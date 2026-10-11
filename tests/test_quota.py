"""Tests for the quota plugin script; both providers are mocked at their boundaries."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/quota/skills/quota/scripts/quota.py"
spec = importlib.util.spec_from_file_location("quota", SCRIPT)
quota = importlib.util.module_from_spec(spec)
sys.modules["quota"] = quota  # dataclasses resolve their module during execution
spec.loader.exec_module(quota)


class AssessTest(unittest.TestCase):
    at = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)

    def reading(self, week=50, elapsed=100, left=68, missing_start=False):
        return quota.Reading(
            provider="codex", at=self.at.timestamp(), five_hour=20,
            five_reset=(self.at + timedelta(hours=2)).isoformat(), week=week,
            week_reset=(self.at + timedelta(hours=left)).isoformat(),
            week_start=None if missing_start else (self.at - timedelta(hours=elapsed)).isoformat(),
            overflow_billed=False,
        )

    def test_projection(self):
        result = quota.assess(self.reading())
        self.assertAlmostEqual(result["weekly_pace_points_per_hour"], 0.5)
        self.assertAlmostEqual(result["projected_week_at_reset"], 84)
        self.assertAlmostEqual(result["projected_unused_at_reset"], 16)
        self.assertEqual(result["hours_to_five_hour_reset"], 2)
        self.assertEqual(result["five_hour_unused"], 80)
        self.assertEqual(result["week_unused"], 50)

    def test_young_window_has_no_pace(self):
        result = quota.assess(self.reading(elapsed=5))
        for key in ("weekly_pace_points_per_hour", "projected_week_at_reset", "projected_unused_at_reset"):
            self.assertIsNone(result[key])

    def test_caps_at_100(self):
        self.assertEqual(quota.assess(self.reading(week=90, elapsed=24, left=144))["projected_week_at_reset"], 100)

    def test_missing_week_start_assumes_7_days(self):
        result = quota.assess(self.reading(week=72, left=24, missing_start=True))
        self.assertAlmostEqual(result["weekly_pace_points_per_hour"], 0.5)
        self.assertAlmostEqual(result["projected_week_at_reset"], 84)


class CodexTest(unittest.TestCase):
    def test_windows_picked_by_length(self):
        snapshot = {
            "rateLimits": {"primary": {"windowDurationMins": 10080, "usedPercent": 30, "resetsAt": 1791806400},
                           "secondary": {"windowDurationMins": 300, "usedPercent": 70, "resetsAt": 1791208800},
                           "planType": "pro", "credits": {"hasCredits": False, "unlimited": False}},
            "rateLimitResetCredits": {"credits": [
                {"status": "available", "title": "banked", "expiresAt": 1791806400},
                {"status": "redeemed", "title": "used", "expiresAt": 1791806400}]},
        }
        with patch.object(quota, "_codex_rpc", return_value=snapshot):
            result = quota.read_codex()
        self.assertEqual(result.five_hour, 70)
        self.assertEqual(result.week, 30)
        self.assertEqual(len(result.reset_credits), 1)
        self.assertEqual(result.reset_credits[0]["title"], "banked")
        self.assertEqual(datetime.fromisoformat(result.week_start), datetime(2026, 10, 5, 12, tzinfo=timezone.utc))
        self.assertFalse(result.overflow_billed)
