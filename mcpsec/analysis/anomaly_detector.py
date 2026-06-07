"""Behavioral anomaly detection with context-aware scoring.

Two layers, fused per the anomaly-detection spec:

1. Predefined "always-flag" rules — fixed frequency thresholds and the
   off-hours window. Work from cold start, set base severity HIGH directly.
2. Adaptive baseline — per-tool online EMA of hourly call rate:
       mu    <- alpha * x + (1 - alpha) * mu
       sigma2 <- alpha * (x - mu)^2 + (1 - alpha) * sigma2
   After warm-up, deviations are z-scored and mapped to a base severity
   (LOW / MEDIUM / HIGH). Samples with |z| > outlier_z are excluded from
   EMA updates so live attacks are never learned as "normal".

Final severity fuses the statistical deviation with static Toxic Flow risk:
       final = clip(base_level * multiplier)  on LOW..CRITICAL
where the multiplier comes from the tool's U/S/E labels (0.5 / 1.0 / 1.5)
or lethal-trifecta path membership (2.0).

The frequency counter is global (session-independent): all tool calls across
all sessions feed the same sliding window. This intentionally catches
swarm/multi-session attacks that stay under per-session thresholds.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("analysis.anomaly_detector")

_SEVERITY_LEVELS: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_LEVEL_NAMES: dict[int, str] = {v: k for k, v in _SEVERITY_LEVELS.items()}


@dataclass
class ToolBaseline:
    """Online EMA baseline of one tool's call rate (calls per hour)."""

    mean: float = 0.0
    var: float = 0.0
    samples: int = 0

    @property
    def std(self) -> float:
        return math.sqrt(max(self.var, 0.0))


@dataclass
class AnomalyResult:
    """Outcome of one anomaly check, including the fused severity."""

    flags: list[str] = field(default_factory=list)
    base_severity: str | None = None    # LOW / MEDIUM / HIGH
    final_severity: str | None = None   # after toxic-flow multiplier + clip
    multiplier: float = 1.0
    z_score: float | None = None
    action: str = "pass"                # pass / log / alert / block

    @property
    def is_blocking(self) -> bool:
        return self.action == "block"


class AnomalyDetector:
    """
    Stateful detector for behavioral anomalies.

    Pass a ToxicFlowLoader (analysis.toxic_flow) to enable severity fusion;
    without it the multiplier is a neutral 1.0.
    """

    def __init__(self, config: Any, toxic_flow_loader: Any | None = None) -> None:
        self._config = config
        self._tf_loader = toxic_flow_loader
        self._started = datetime.now(tz=timezone.utc)
        # Deque of UTC timestamps for all tool calls (global, predefined rules)
        self._timestamps: deque[datetime] = deque()
        # Per-tool timestamps + learned EMA baselines (adaptive layer)
        self._tool_timestamps: dict[str, deque[datetime]] = {}
        self._baselines: dict[str, ToolBaseline] = {}

    def check(self, tool_name: str = "") -> AnomalyResult:
        """
        Record one tool-call and return the scored anomaly result.

        Possible flags:
          - "high_frequency"   — predefined global rate limit exceeded
          - "off_hours_access" — call inside configured off-hours window
          - "freq_zscore:<tool>:<z>" — adaptive per-tool frequency deviation
        """
        now = datetime.now(tz=timezone.utc)
        result = AnomalyResult()
        base_level = 0

        # --- Predefined layer (always-flag -> base severity HIGH) ---------
        if self._config.frequency.enabled:
            flag = self._check_frequency(now)
            if flag:
                result.flags.append(flag)
                base_level = max(base_level, _SEVERITY_LEVELS["HIGH"])

        if self._config.off_hours.enabled and self._is_off_hours(now):
            result.flags.append("off_hours_access")
            base_level = max(base_level, _SEVERITY_LEVELS["HIGH"])

        # --- Adaptive layer (EMA baseline + z-score) ----------------------
        if tool_name and self._config.learning.enabled:
            z, level = self._check_adaptive(tool_name, now)
            if z is not None:
                result.z_score = z
            if level > 0:
                result.flags.append(f"freq_zscore:{tool_name}:{z:.1f}")
                base_level = max(base_level, level)

        if base_level == 0:
            return result

        # --- Severity fusion: final = clip(base * multiplier) -------------
        result.base_severity = _LEVEL_NAMES[base_level]
        result.multiplier = self._toxic_multiplier(tool_name)
        final_level = min(max(int(base_level * result.multiplier + 0.5), 1), 4)
        result.final_severity = _LEVEL_NAMES[final_level]
        result.action = getattr(
            self._config.severity_actions, result.final_severity.lower(), "alert"
        )
        return result

    # ------------------------------------------------------------------
    # Predefined frequency
    # ------------------------------------------------------------------

    def _check_frequency(self, now: datetime) -> str | None:
        self._timestamps.append(now)

        # Trim entries older than 1 hour
        cutoff_1h = now.timestamp() - 3600
        while self._timestamps and self._timestamps[0].timestamp() < cutoff_1h:
            self._timestamps.popleft()

        per_hour = len(self._timestamps)
        if per_hour > self._config.frequency.max_per_hour:
            logger.warning(
                "Anomaly: high_frequency — %d calls in last hour (limit %d)",
                per_hour,
                self._config.frequency.max_per_hour,
            )
            return "high_frequency"

        cutoff_1m = now.timestamp() - 60
        per_minute = sum(1 for t in self._timestamps if t.timestamp() >= cutoff_1m)
        if per_minute > self._config.frequency.max_per_minute:
            logger.warning(
                "Anomaly: high_frequency — %d calls in last minute (limit %d)",
                per_minute,
                self._config.frequency.max_per_minute,
            )
            return "high_frequency"

        return None

    # ------------------------------------------------------------------
    # Adaptive baseline (per-tool EMA + z-score)
    # ------------------------------------------------------------------

    def _check_adaptive(self, tool_name: str, now: datetime) -> tuple[float | None, int]:
        """
        Record the call, score it against the learned baseline, update the EMA.

        Returns (z_score, severity_level). z_score is None and level 0 while
        the baseline is still warming up.
        """
        cfg = self._config.learning
        ts = self._tool_timestamps.setdefault(tool_name, deque())
        ts.append(now)
        cutoff_1h = now.timestamp() - 3600
        while ts and ts[0].timestamp() < cutoff_1h:
            ts.popleft()
        x = float(len(ts))  # observed calls/hour for this tool

        bl = self._baselines.setdefault(tool_name, ToolBaseline())
        warmed_up = (
            (now - self._started).total_seconds() >= cfg.warmup_hours * 3600
            and bl.samples >= cfg.min_data_points
        )

        z: float | None = None
        level = 0
        if warmed_up:
            denom = bl.std if bl.std > 1e-6 else 1.0
            z = (x - bl.mean) / denom
            zt = self._config.z_thresholds
            az = abs(z)
            if az >= zt.high:
                level = _SEVERITY_LEVELS["HIGH"]
            elif az >= zt.medium:
                level = _SEVERITY_LEVELS["MEDIUM"]
            elif az >= zt.low:
                level = _SEVERITY_LEVELS["LOW"]
            if level > 0:
                logger.warning(
                    "Anomaly: freq_zscore — tool=%s observed=%.0f/h baseline=%.1f±%.1f z=%.1f",
                    tool_name, x, bl.mean, bl.std, z,
                )

        # Outlier exclusion: never learn an active attack as "normal"
        if warmed_up and z is not None and abs(z) > cfg.outlier_z:
            return z, level

        # EMA update (spec order: mean first, then variance with new mean)
        a = cfg.alpha
        bl.mean = a * x + (1 - a) * bl.mean
        bl.var = a * (x - bl.mean) ** 2 + (1 - a) * bl.var
        bl.samples += 1
        return z, level

    # ------------------------------------------------------------------
    # Toxic Flow severity fusion
    # ------------------------------------------------------------------

    def _toxic_multiplier(self, tool_name: str) -> float:
        tf_cfg = self._config.toxic_flow_integration
        if not tool_name or self._tf_loader is None or not tf_cfg.enabled:
            return 1.0
        try:
            return self._tf_loader.get_severity_multiplier(
                tool_name, tf_cfg.multipliers.model_dump()
            )
        except Exception as exc:
            logger.warning("Toxic flow multiplier lookup failed: %s", exc)
            return 1.0

    # ------------------------------------------------------------------
    # Off-hours
    # ------------------------------------------------------------------

    def _is_off_hours(self, now: datetime) -> bool:
        hour = now.hour
        start = self._config.off_hours.start_hour
        end = self._config.off_hours.end_hour

        if start <= end:
            # Simple range: e.g., 0–6 (midnight to 6am)
            return start <= hour < end
        else:
            # Wraps midnight: e.g., 22–6 (10pm to 6am)
            return hour >= start or hour < end
