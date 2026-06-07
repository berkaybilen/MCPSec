"""Unit tests for context-aware anomaly scoring (EMA + z-score + toxic-flow fusion).

Validates the spec examples from anomaly-detection-final.md:
  - EMA update: 0.1 * 10 + 0.9 * 8.0 = 8.2
  - MEDIUM x 0.5 = LOW       (harmless tool, frequency spike)
  - HIGH   x 2.0 = CRITICAL  (lethal-trifecta member, sensitive access)
  - HIGH   x 1.5 = CRITICAL  (dual combination)
  - Outlier exclusion: |z| > 5 samples never update the baseline
  - Warmup: no z-scoring before warmup_hours + min_data_points
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcpsec"))

from analysis.anomaly_detector import AnomalyDetector, ToolBaseline  # noqa: E402
from config import AnomalyDetectionConfig  # noqa: E402


class FakeLoader:
    """Stands in for ToxicFlowLoader with a fixed multiplier."""

    def __init__(self, multiplier: float) -> None:
        self._m = multiplier

    def get_severity_multiplier(self, tool_name: str, multipliers=None) -> float:
        return self._m


def make_detector(multiplier: float = 1.0, **learning_overrides) -> AnomalyDetector:
    cfg = AnomalyDetectionConfig(
        frequency={"enabled": False},
        off_hours={"enabled": False},
        learning={"warmup_hours": 0, "min_data_points": 1, **learning_overrides},
    )
    return AnomalyDetector(cfg, FakeLoader(multiplier))


def prime_baseline(det: AnomalyDetector, tool: str, mean: float, std: float, samples: int = 200):
    det._baselines[tool] = ToolBaseline(mean=mean, var=std**2, samples=samples)


class TestEMA(unittest.TestCase):
    def test_spec_example_ema_update(self):
        """Spec: old mean 8.0, observed 10, alpha 0.1 -> new mean 8.2."""
        det = make_detector()
        prime_baseline(det, "read_file", mean=8.0, std=4.0)
        # Force observed x=10 by pre-filling 9 timestamps (check() adds the 10th)
        from collections import deque
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        det._tool_timestamps["read_file"] = deque([now] * 9)
        det.check("read_file")
        bl = det._baselines["read_file"]
        self.assertAlmostEqual(bl.mean, 0.1 * 10 + 0.9 * 8.0, places=6)  # 8.2

    def test_outlier_excluded_from_learning(self):
        """|z| > 5 must NOT update the baseline (attacks aren't learned)."""
        det = make_detector()
        prime_baseline(det, "send_email", mean=1.2, std=0.6)
        from collections import deque
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        det._tool_timestamps["send_email"] = deque([now] * 14)  # x=15, z=(15-1.2)/0.6=23
        res = det.check("send_email")
        bl = det._baselines["send_email"]
        self.assertAlmostEqual(bl.mean, 1.2, places=6)  # unchanged
        self.assertGreater(abs(res.z_score), 5)
        self.assertEqual(res.base_severity, "HIGH")

    def test_warmup_no_scoring(self):
        """During warmup the detector learns but never flags."""
        det = make_detector(warmup_hours=24, min_data_points=100)
        prime_baseline(det, "t", mean=0.0, std=0.1, samples=0)
        res = det.check("t")
        self.assertIsNone(res.z_score)
        self.assertEqual(res.flags, [])
        self.assertEqual(det._baselines["t"].samples, 1)  # learned


class TestSeverityFusion(unittest.TestCase):
    def _scored(self, multiplier: float, mean: float, std: float, x: int, tool="t"):
        det = make_detector(multiplier)
        prime_baseline(det, tool, mean=mean, std=std)
        from collections import deque
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        det._tool_timestamps[tool] = deque([now] * (x - 1))
        return det.check(tool)

    def test_spec_example_1_medium_x_05_is_low(self):
        """format_text: MEDIUM deviation x 0.5 (no label) -> LOW."""
        # mean=5, std=1.25, x=10 -> z=4.0 -> MEDIUM
        res = self._scored(0.5, mean=5.0, std=1.25, x=10)
        self.assertEqual(res.base_severity, "MEDIUM")
        self.assertEqual(res.final_severity, "LOW")
        self.assertEqual(res.action, "log")

    def test_spec_example_2_high_x_20_is_critical(self):
        """read_file on trifecta path: HIGH x 2.0 -> CRITICAL."""
        # z >= 5 -> HIGH
        res = self._scored(2.0, mean=1.2, std=0.6, x=15)
        self.assertEqual(res.base_severity, "HIGH")
        self.assertEqual(res.final_severity, "CRITICAL")
        self.assertEqual(res.action, "block")
        self.assertTrue(res.is_blocking)

    def test_spec_example_3_high_x_15_is_critical(self):
        """Dual combination: HIGH x 1.5 -> CRITICAL (3 * 1.5 = 4.5 -> 4)."""
        res = self._scored(1.5, mean=1.2, std=0.6, x=15)
        self.assertEqual(res.base_severity, "HIGH")
        self.assertEqual(res.final_severity, "CRITICAL")

    def test_low_x_10_stays_low(self):
        # z in [2,3) -> LOW; x=8, mean=5, std=1.25 -> z=2.4
        res = self._scored(1.0, mean=5.0, std=1.25, x=8)
        self.assertEqual(res.base_severity, "LOW")
        self.assertEqual(res.final_severity, "LOW")

    def test_clip_floor(self):
        """LOW x 0.5 = 0.5 -> clipped to LOW, never below the ladder."""
        res = self._scored(0.5, mean=5.0, std=1.25, x=8)
        self.assertEqual(res.base_severity, "LOW")
        self.assertEqual(res.final_severity, "LOW")


class TestPredefinedAlwaysFlag(unittest.TestCase):
    def test_predefined_frequency_sets_high_base(self):
        cfg = AnomalyDetectionConfig(
            frequency={"enabled": True, "max_per_minute": 2, "max_per_hour": 500},
            off_hours={"enabled": False},
            learning={"enabled": False},
        )
        det = AnomalyDetector(cfg, FakeLoader(2.0))
        det.check("read_file")
        det.check("read_file")
        res = det.check("read_file")  # 3rd call in a minute > limit 2
        self.assertIn("high_frequency", res.flags)
        self.assertEqual(res.base_severity, "HIGH")
        self.assertEqual(res.final_severity, "CRITICAL")  # HIGH x 2.0


if __name__ == "__main__":
    unittest.main(verbosity=2)
