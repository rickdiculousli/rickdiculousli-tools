#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""How much of the Claude and Codex subscriptions is left, and how much will go unused at the reset.

Each provider is read the way its own client reads it, and neither read costs tokens:

- Claude: the page Claude Code's `/usage` screen reads (`/api/oauth/usage`), with the login
  Claude Code already keeps (macOS keychain, or ~/.claude/.credentials.json on Linux). Adapted
  from the usage gate in a private project. The page is
  undocumented.
- Codex: `account/rateLimits/read` on Codex's own app server (`codex app-server`, JSON-RPC over
  stdio), the same call the Codex TUI and desktop app make. Codex handles its own auth.

It reports numbers, not rulings: how much of each window is used, when each resets, the pace
across the weekly window, and how much is projected to be left at the reset. Whoever reads it
decides what to do. Each reading is logged to
${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/quota/usage.jsonl.

    uv run --script quota.py                    # both providers, human-readable
    uv run --script quota.py --provider codex   # one provider
    uv run --script quota.py --json             # the same as JSON, for agents
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROVIDERS = ("claude", "codex")

MIN_ELAPSED_H = 12.0    # a weekly window younger than this is too short to project a pace from

STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
LOG = STATE / "rickdiculousli-tools" / "quota" / "usage.jsonl"


class Unknown(Exception):
    """A provider's limits couldn't be read; the reason is the message."""


@dataclass
class Reading:
    provider: str
    at: float
    five_hour: float
    five_reset: str | None
    week: float
    week_reset: str | None
    week_start: str | None
    overflow_billed: bool             # past 100%, work is billed rather than refused
    plan: str | None = None
    reset_credits: list[dict] = field(default_factory=list)   # banked resets (Codex)


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


# ---- Claude -------------------------------------------------------------------------------

CLAUDE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN = "Claude Code-credentials"                          # macOS
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"   # Linux


def _claude_token() -> str:
    raw = None
    if sys.platform == "darwin":
        p = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN, "-w"],
                           capture_output=True, text=True)
        raw = p.stdout if p.returncode == 0 else None
    if raw is None and CREDENTIALS.exists():
        raw = CREDENTIALS.read_text()
    if raw is None:
        raise Unknown("no Claude Code login found (keychain or ~/.claude/.credentials.json)")
    try:
        o = json.loads(raw)["claudeAiOauth"]
    except (ValueError, KeyError):
        raise Unknown("the stored Claude Code login isn't in the expected shape") from None
    if o.get("expiresAt", 0) / 1000 < time.time():
        raise Unknown("the Claude Code login has expired; opening Claude Code once refreshes it")
    return o["accessToken"]


def read_claude() -> Reading:
    req = urllib.request.Request(CLAUDE_URL, headers={"Authorization": f"Bearer {_claude_token()}",
                                                      "anthropic-beta": "oauth-2025-04-20"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise Unknown(f"usage page: {e}") from None
    try:
        return Reading(
            provider="claude",
            at=time.time(),
            five_hour=float(d["five_hour"]["utilization"]),
            five_reset=d["five_hour"].get("resets_at"),
            week=float(d["seven_day"]["utilization"]),
            week_reset=d["seven_day"].get("resets_at"),
            week_start=(d.get("seven_day_breakdown") or {}).get("window_started_at"),
            overflow_billed=bool((d.get("extra_usage") or {}).get("is_enabled")),
        )
    except (KeyError, TypeError, ValueError):
        raise Unknown("the usage page changed shape") from None


# ---- Codex --------------------------------------------------------------------------------

CODEX_TIMEOUT = 30


def _codex_rpc(method: str, params: dict | None = None) -> dict:
    """One request to a short-lived `codex app-server`. It exits when stdin closes, even with a
    request in flight, so stdin stays open until the answer arrives."""
    exe = shutil.which("codex")
    if exe is None:
        raise Unknown("the codex CLI isn't installed")
    p = subprocess.Popen([exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True)
    lines: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        for line in p.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()

    def send(o: dict) -> None:
        p.stdin.write(json.dumps(o) + "\n")
        p.stdin.flush()

    def answer(i: int, deadline: float) -> dict:
        while True:
            try:
                line = lines.get(timeout=max(deadline - time.time(), 0))
            except queue.Empty:
                raise Unknown(f"codex app-server didn't answer {method} within {CODEX_TIMEOUT}s") from None
            if line is None:
                raise Unknown("codex app-server exited before answering")
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("id") == i:
                if "error" in m:
                    raise Unknown(f"codex app-server: {m['error'].get('message', m['error'])}")
                return m["result"]

    try:
        deadline = time.time() + CODEX_TIMEOUT
        send({"id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "rickdiculousli-tools-quota", "version": "1"}}})
        answer(1, deadline)
        send({"method": "initialized"})
        send({"id": 2, "method": method, **({"params": params} if params else {})})
        return answer(2, deadline)
    finally:
        try:
            p.stdin.close()
            p.wait(timeout=5)
        except Exception:
            p.kill()


def read_codex() -> Reading:
    d = _codex_rpc("account/rateLimits/read")
    snap = (d.get("rateLimitsByLimitId") or {}).get("codex") or d.get("rateLimits") or {}
    windows = [w for w in (snap.get("primary"), snap.get("secondary")) if w]
    if not windows:
        raise Unknown("codex reported no rate-limit windows (is it logged in with ChatGPT?)")
    # Pick the windows by length rather than trusting primary/secondary order.
    five = min(windows, key=lambda w: w.get("windowDurationMins") or 0)
    week = max(windows, key=lambda w: w.get("windowDurationMins") or 0)
    week_reset = week.get("resetsAt")
    week_mins = week.get("windowDurationMins")
    credits = snap.get("credits") or {}
    banked = [c for c in ((d.get("rateLimitResetCredits") or {}).get("credits") or [])
              if c.get("status") == "available"]
    return Reading(
        provider="codex",
        at=time.time(),
        five_hour=float(five["usedPercent"]),
        five_reset=_iso(five.get("resetsAt")),
        week=float(week["usedPercent"]),
        week_reset=_iso(week_reset),
        week_start=_iso(week_reset - week_mins * 60) if week_reset and week_mins else None,
        overflow_billed=bool(credits.get("hasCredits") or credits.get("unlimited")),
        plan=snap.get("planType"),
        reset_credits=[{"title": c.get("title"), "expires": _iso(c.get("expiresAt"))} for c in banked],
    )


READERS = {"claude": read_claude, "codex": read_codex}


# ---- assessment ---------------------------------------------------------------------------

def record(r: Reading) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({**asdict(r), "pid": os.getpid()}) + "\n")


def _ts(iso: str | None) -> float | None:
    return datetime.fromisoformat(iso).timestamp() if iso else None


def local(iso: str | None) -> str:
    if not iso:
        return "unknown"
    t = datetime.fromisoformat(iso).astimezone()
    return t.strftime("%H:%M today") if t.date() == datetime.now().date() else t.strftime("%a %m-%d %H:%M")


def assess(r: Reading) -> dict:
    """Facts derived from a reading: time left, pace across the weekly window, and where it lands."""
    reset, start = _ts(r.week_reset), _ts(r.week_start)
    hours_left = max((reset - r.at) / 3600, 0) if reset else None
    if start is None and reset is not None:
        start = reset - 7 * 86400
    elapsed_h = (r.at - start) / 3600 if start else None
    pace = r.week / elapsed_h if elapsed_h and elapsed_h >= MIN_ELAPSED_H else None      # points/hour
    projected = min(r.week + pace * hours_left, 100.0) if pace is not None and hours_left is not None else None
    return {
        "five_hour_unused": 100 - r.five_hour,
        "week_unused": 100 - r.week,
        "hours_to_five_hour_reset": max((_ts(r.five_reset) - r.at) / 3600, 0) if r.five_reset else None,
        "hours_to_weekly_reset": hours_left,
        "weekly_pace_points_per_hour": pace,
        "projected_week_at_reset": projected,
        "projected_unused_at_reset": 100 - projected if projected is not None else None,
    }


def show(r: Reading, a: dict) -> str:
    f = lambda v, fmt: "?" if v is None else format(v, fmt)
    title = r.provider.capitalize() + (f" ({r.plan})" if r.plan else "")
    lines = [
        title,
        f"  5-hour window  {r.five_hour:5.0f}% used   resets {local(r.five_reset)} "
        f"({f(a['hours_to_five_hour_reset'], '.1f')}h)",
        f"  weekly window  {r.week:5.0f}% used   resets {local(r.week_reset)} "
        f"({f(a['hours_to_weekly_reset'], '.0f')}h)",
        f"  weekly pace    {f(a['weekly_pace_points_per_hour'], '.2f')} points/hour; at that pace "
        f"{f(a['projected_week_at_reset'], '.0f')}% used by the reset, "
        f"{f(a['projected_unused_at_reset'], '.0f')} points unused",
        f"  overflow       {'billed past 100%' if r.overflow_billed else 'refused past 100% (no billing)'}",
    ]
    if r.reset_credits:
        soonest = min((c["expires"] for c in r.reset_credits if c["expires"]), default=None)
        lines.append(f"  banked resets  {len(r.reset_credits)} available"
                     + (f", first expires {local(soonest)}" if soonest else ""))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", choices=(*PROVIDERS, "all"), default="all")
    ap.add_argument("--json", action="store_true", help="print the readings and derived numbers as JSON")
    args = ap.parse_args()

    names = PROVIDERS if args.provider == "all" else (args.provider,)
    results = []
    for name in names:
        try:
            r = READERS[name]()
        except Unknown as e:
            print(f"quota: could not read the {name} limits ({e})", file=sys.stderr)
            continue
        record(r)
        results.append((r, assess(r)))

    if args.json:
        print(json.dumps([{"reading": asdict(r), **a} for r, a in results], indent=2))
    else:
        print(f"Usage, {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("\n".join(show(r, a) for r, a in results))
    return 0 if results else 2


if __name__ == "__main__":
    sys.exit(main())
