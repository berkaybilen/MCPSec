"""Behavioral anomaly detection: call frequency and off-hours access."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("analysis.anomaly_detector")


class AnomalyDetector:
    """
    Stateful detector for behavioral anomalies.

    Frequency counter is global (session-independent): all tool calls across
    all sessions feed into the same sliding window. This intentionally catches
    swarm/multi-session attacks that stay under per-session thresholds.
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        # Deque of UTC timestamps for all tool calls (global)
        self._timestamps: deque[datetime] = deque()

    def check(self) -> list[str]:
        """
        Record one tool-call and return any anomaly flags.

        Returns a list containing zero or more of:
          - "high_frequency"   — calls exceed rate limits
          - "off_hours_access" — call falls inside configured off-hours window
        """
        now = datetime.now(tz=timezone.utc)
        flags: list[str] = []

        if self._config.frequency.enabled:
            flag = self._check_frequency(now)
            if flag:
                flags.append(flag)

        if self._config.off_hours.enabled:
            if self._is_off_hours(now):
                flags.append("off_hours_access")

        return flags

    # ------------------------------------------------------------------
    # Frequency
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
