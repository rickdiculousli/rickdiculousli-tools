"""Tests for the quota plugin script; both providers are mocked at their boundaries."""

from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/quota/skills/quota/scripts/quota.py"
spec = importlib.util.spec_from_file_location("quota", SCRIPT)
quota = importlib.util.module_from_spec(spec)
sys.modules["quota"] = quota  # dataclasses resolve their module during execution
spec.loader.exec_module(quota)


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(quota.os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.home = patch.object(quota.Path, "home", return_value=self.root)
        self.home.start()
        self.addCleanup(self.home.stop)

    def credentials(self, path, token):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"claudeAiOauth": {
            "accessToken": token, "expiresAt": (time.time() + 3600) * 1000,
        }}), encoding="utf-8")

    def test_custom_profile_uses_its_own_credentials(self):
        profile = self.root / "custom profile"
        self.credentials(profile / ".credentials.json", "custom")
        quota.os.environ["CLAUDE_CONFIG_DIR"] = str(profile)
        with patch.object(quota.sys, "platform", "linux"):
            self.assertEqual(quota._claude_token(), "custom")

    def test_explicit_file_takes_precedence_over_keychain(self):
        path = self.root / "selected.json"
        self.credentials(path, "selected")
        quota.os.environ["QUOTA_CLAUDE_CREDENTIALS_FILE"] = str(path)
        with patch.object(quota.sys, "platform", "darwin"), patch.object(
            quota.subprocess, "run", side_effect=AssertionError("must use selected file")
        ):
            self.assertEqual(quota._claude_token(), "selected")

    def test_missing_custom_profile_does_not_read_default_account(self):
        self.credentials(self.root / ".claude" / ".credentials.json", "wrong-account")
        quota.os.environ["CLAUDE_CONFIG_DIR"] = str(self.root / "missing")
        with patch.object(quota.sys, "platform", "darwin"), patch.object(
            quota.subprocess, "run", side_effect=AssertionError("must not read default keychain")
        ):
            with self.assertRaises(quota.Unknown):
                quota._claude_token()

    def test_oauth_environment_token(self):
        quota.os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "environment-token"
        with patch.object(quota.sys, "platform", "linux"):
            self.assertEqual(quota._claude_token(), "environment-token")

    def test_unreadable_explicit_file_reports_unknown(self):
        quota.os.environ["QUOTA_CLAUDE_CREDENTIALS_FILE"] = str(self.root / "missing.json")
        with patch.object(quota.sys, "platform", "linux"):
            with self.assertRaises(quota.Unknown):
                quota._claude_token()

    def test_custom_keychain_service_selects_credentials(self):
        quota.os.environ["CLAUDE_CONFIG_DIR"] = str(self.root / "profile")
        quota.os.environ["QUOTA_CLAUDE_KEYCHAIN_SERVICE"] = "selected-service"
        def keychain(args, **kwargs):
            if args != ["security", "find-generic-password", "-s", "selected-service", "-w"]:
                raise AssertionError("wrong keychain service")
            raw = json.dumps({"claudeAiOauth": {"accessToken": "selected-keychain",
                              "expiresAt": (time.time() + 3600) * 1000}})
            return quota.subprocess.CompletedProcess(args, 0, stdout=raw)
        with patch.object(quota.sys, "platform", "darwin"), patch.object(
            quota.subprocess, "run", side_effect=keychain
        ):
            self.assertEqual(quota._claude_token(), "selected-keychain")

    def test_missing_explicit_keychain_does_not_read_default_account(self):
        self.credentials(self.root / ".claude" / ".credentials.json", "wrong-account")
        quota.os.environ["QUOTA_CLAUDE_KEYCHAIN_SERVICE"] = "missing-service"
        with patch.object(quota.sys, "platform", "darwin"), patch.object(
            quota.subprocess, "run", return_value=quota.subprocess.CompletedProcess([], 1, stdout="")
        ):
            with self.assertRaises(quota.Unknown):
                quota._claude_token()

    def test_default_file_login(self):
        self.credentials(self.root / ".claude" / ".credentials.json", "default-account")
        with patch.object(quota.sys, "platform", "linux"):
            self.assertEqual(quota._claude_token(), "default-account")

    def test_invalid_utf8_credentials_report_unknown(self):
        path = self.root / "invalid.json"
        path.write_bytes(b"\xff")
        quota.os.environ["QUOTA_CLAUDE_CREDENTIALS_FILE"] = str(path)
        with patch.object(quota.sys, "platform", "linux"):
            with self.assertRaises(quota.Unknown):
                quota._claude_token()


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

    def test_utc_z_reset_timestamps_are_supported(self):
        reading = self.reading()
        reading.five_reset = "2026-10-05T14:00:00Z"
        reading.week_reset = "2026-10-08T08:00:00Z"
        reading.week_start = "2026-10-01T08:00:00Z"
        assessment = quota.assess(reading)
        self.assertEqual(assessment["hours_to_five_hour_reset"], 2)
        self.assertEqual(assessment["hours_to_weekly_reset"], 68)
        self.assertIn("2.0h", quota.show(reading, assessment))


class ClaudeTest(unittest.TestCase):
    page = {"seven_day": {"utilization": 10.0, "resets_at": "2026-11-11T03:00:01+00:00"},
            "seven_day_breakdown": {"window_started_at": "2026-11-04T03:00:01+00:00"},
            "extra_usage": {"is_enabled": False}}

    def read(self, page):
        body = io.BytesIO(json.dumps(page).encode())
        with patch.object(quota, "_claude_token", return_value="token"), patch.object(
            quota.urllib.request, "urlopen", return_value=body
        ):
            return quota.read_claude()

    def test_plan_without_a_five_hour_window(self):
        reading = self.read({**self.page, "five_hour": None})
        self.assertIsNone(reading.five_hour)
        self.assertIsNone(reading.five_reset)
        self.assertEqual(reading.week, 10)
        assessment = quota.assess(reading)
        self.assertIsNone(assessment["five_hour_unused"])
        self.assertIsNone(assessment["hours_to_five_hour_reset"])
        self.assertEqual(assessment["week_unused"], 90)
        self.assertIn("5-hour window   none on this plan", quota.show(reading, assessment))
        json.dumps(quota.asdict(reading))

    def test_plan_with_a_five_hour_window(self):
        reading = self.read({**self.page, "five_hour": {
            "utilization": 9.0, "resets_at": "2026-11-04T11:00:00+00:00"}})
        self.assertEqual(reading.five_hour, 9)
        self.assertEqual(reading.five_reset, "2026-11-04T11:00:00+00:00")

    def test_missing_five_hour_key_is_a_changed_page(self):
        with self.assertRaises(quota.Unknown):
            self.read(self.page)


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


class ClaudeScopedTest(unittest.TestCase):
    page = {"five_hour": None,
            "seven_day": {"utilization": 76.0, "resets_at": "2026-11-11T03:00:00.177821+00:00"},
            "seven_day_breakdown": {"window_started_at": "2026-11-04T03:00:00.177821+00:00"},
            "seven_day_opus": None, "seven_day_sonnet": None,
            "extra_usage": {"is_enabled": False}}
    limits = [
        {"kind": "weekly_all", "group": "weekly", "percent": 76, "severity": "warning",
         "resets_at": "2026-11-11T03:00:00.177821+00:00", "scope": None, "is_active": False},
        {"kind": "weekly_scoped", "group": "weekly", "percent": 89, "severity": "warning",
         "resets_at": "2026-11-11T03:00:00.178047+00:00",
         "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None}, "is_active": True},
    ]
    at = datetime(2026, 11, 10, 20, tzinfo=timezone.utc).timestamp()

    def read(self, page):
        body = io.BytesIO(json.dumps(page).encode())
        with patch.object(quota, "_claude_token", return_value="token"), patch.object(
            quota.urllib.request, "urlopen", return_value=body
        ), patch.object(quota.time, "time", return_value=self.at):
            return quota.read_claude()

    def test_scoped_weekly_limit_is_read_and_marked_binding(self):
        reading = self.read({**self.page, "limits": self.limits,
                             "weekly_scoped_shares": [{"limit_index": 1, "used_percent_of_weekly": 45,
                                                       "allowance_percent_of_weekly": 50}]})
        self.assertEqual(reading.week, 76)
        self.assertEqual(reading.scoped, [{"name": "Fable", "group": "weekly", "percent": 89,
                                           "resets_at": "2026-11-11T03:00:00.178047+00:00",
                                           "binding": True}])
        assessment = quota.assess(reading)
        (fable,) = assessment["scoped"]
        self.assertTrue(fable["window_start_known"])
        self.assertAlmostEqual(fable["hours_to_reset"], 7, places=2)
        self.assertAlmostEqual(fable["pace_points_per_hour"], 89 / 161, places=4)
        self.assertAlmostEqual(fable["projected_at_reset"], 89 + 89 / 161 * 7, places=3)
        text = quota.show(reading, assessment)
        self.assertRegex(text, r"\n  Fable weekly      89% used   resets .* \(7h\)  ← binding\n")
        self.assertIn("\n  Fable pace     0.55 points/hour", text)
        json.dumps({"reading": quota.asdict(reading), **assessment})

    def test_scoped_limit_with_another_reset_has_no_pace(self):
        limit = {**self.limits[1], "resets_at": "2026-11-12T03:00:00+00:00"}
        reading = self.read({**self.page, "limits": [limit]})
        (scoped,) = quota.assess(reading)["scoped"]
        self.assertFalse(scoped["window_start_known"])
        self.assertIsNone(scoped["pace_points_per_hour"])
        self.assertIsNone(scoped["projected_at_reset"])
        self.assertNotIn("Fable pace", quota.show(reading, quota.assess(reading)))

    def test_model_windows_are_read_when_present(self):
        reading = self.read({**self.page, "limits": self.limits,
                             "seven_day_opus": {"utilization": 40.0, "resets_at": "2026-11-11T03:00:00+00:00"}})
        self.assertEqual([s["name"] for s in reading.scoped], ["Fable", "Opus"])
        self.assertFalse(reading.scoped[1]["binding"])

    def test_no_limits_reads_as_before(self):
        reading = self.read(self.page)
        self.assertEqual(reading.scoped, [])
        assessment = quota.assess(reading)
        self.assertEqual(assessment["scoped"], [])
        self.assertEqual(quota.show(reading, assessment).count("\n"), 4)

    def test_malformed_limits_are_ignored(self):
        for limits in ("nope", {"kind": "weekly_scoped"}, None, 5):
            self.assertEqual(self.read({**self.page, "limits": limits}).scoped, [])
        bad = [
            "nope", None, 7,
            {"kind": "weekly_scoped", "percent": "89", "scope": {"model": {"display_name": "Fable"}}},
            {"kind": "weekly_scoped", "percent": True, "scope": {"model": {"display_name": "Fable"}}},
            {"kind": "weekly_scoped", "percent": 89, "scope": {"model": {"display_name": None}}},
            {"kind": "weekly_scoped", "percent": 89, "scope": "Fable"},
            {"kind": "weekly_scoped", "percent": 89},
        ]
        reading = self.read({**self.page, "limits": bad + [
            {"kind": "weekly_scoped", "percent": 50, "resets_at": "not a date", "is_active": "yes",
             "scope": {"model": None, "surface": "web"}}]})
        self.assertEqual(reading.scoped, [{"name": "web", "group": "limit", "percent": 50,
                                           "resets_at": None, "binding": False}])
        assessment = quota.assess(reading)
        self.assertIsNone(assessment["scoped"][0]["hours_to_reset"])
        self.assertIn("web limit         50% used   resets unknown (?h)\n", quota.show(reading, assessment))
        self.assertEqual(self.read({**self.page, "seven_day_opus": {"utilization": None}}).scoped, [])
