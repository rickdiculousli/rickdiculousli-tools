#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""How much of the Claude, Codex, and Antigravity subscriptions is left, and how much will go unused at the reset.

Each provider is read the way its own client reads it, and none of the reads cost tokens:

- Claude: the page Claude Code's `/usage` screen reads (`/api/oauth/usage`), with the login
  Claude Code already keeps (macOS keychain, or ~/.claude/.credentials.json on Linux). The page
  is undocumented.
- Codex: `account/rateLimits/read` on Codex's own app server (`codex app-server`, JSON-RPC over
  stdio), the same call the Codex TUI and desktop app make. Codex handles its own auth.
- Antigravity: `agy --print /usage --output-format json` (and `/credits` for G1 AI credits),
  using the login the `agy` CLI already keeps.

It reports numbers, not rulings: how much of each window is used, when each resets, the pace
across the weekly window, and how much is projected to be left at the reset. Claude's scoped
weekly limits (one model's allowance, say) and Antigravity's separate model-group pools are shown
beside the primary windows, with any binding limit marked. Whoever reads it
decides what to do. Each reading is logged to
${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/quota/usage.jsonl.

    uv run --script quota.py                        # all providers, human-readable
    uv run --script quota.py --provider antigravity # one provider
    uv run --script quota.py --json                 # the same as JSON, for agents
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

PROVIDERS = ("claude", "codex", "antigravity")

MIN_ELAPSED_H = 12.0    # a weekly window younger than this is too short to project a pace from
SAME_RESET_S = 60.0     # a scoped limit resetting this close to the weekly window shares its start

STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
LOG = STATE / "rickdiculousli-tools" / "quota" / "usage.jsonl"


class Unknown(Exception):
    """A provider's limits couldn't be read; the reason is the message."""


@dataclass
class Reading:
    provider: str
    at: float
    five_hour: float | None           # None: the plan has no 5-hour window
    five_reset: str | None
    week: float
    week_reset: str | None
    week_start: str | None
    overflow_billed: bool             # past 100%, work is billed rather than refused
    plan: str | None = None
    reset_credits: list[dict] = field(default_factory=list)   # banked resets (Codex)
    scoped: list[dict] = field(default_factory=list)  # {name, group, percent, resets_at, binding} (Claude, Antigravity)
    scope: str | None = None          # primary model group when windows cover one pool (Antigravity)
    credits: float | None = None      # remaining AI/G1 credits (Antigravity)


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


# ---- Claude -------------------------------------------------------------------------------

CLAUDE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN = "Claude Code-credentials"                          # macOS


def _claude_token() -> str:
    explicit_file = os.environ.get("QUOTA_CLAUDE_CREDENTIALS_FILE")
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if token and not explicit_file:
        return token
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    credentials = (Path(explicit_file).expanduser() if explicit_file else
                   (Path(config).expanduser() if config else Path.home() / ".claude")
                   / ".credentials.json")
    service = os.environ.get("QUOTA_CLAUDE_KEYCHAIN_SERVICE")
    raw = None
    if sys.platform == "darwin" and not explicit_file and (service or not config):
        try:
            p = subprocess.run(["security", "find-generic-password", "-s", service or KEYCHAIN, "-w"],
                               capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            p = None
        raw = p.stdout if p is not None and p.returncode == 0 else None
    if service and not explicit_file and raw is None:
        raise Unknown("cannot read the selected Claude Keychain service; set "
                      "QUOTA_CLAUDE_CREDENTIALS_FILE for a file-based login")
    if raw is None:
        try:
            raw = credentials.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise Unknown("cannot read Claude credentials at the selected location; log in there or set "
                          "QUOTA_CLAUDE_CREDENTIALS_FILE or QUOTA_CLAUDE_KEYCHAIN_SERVICE") from None
    try:
        o = json.loads(raw)["claudeAiOauth"]
        expires = float(o.get("expiresAt", 0)) / 1000
        token = o["accessToken"]
        if not isinstance(token, str) or not token:
            raise ValueError("missing token")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise Unknown("the stored Claude Code login isn't in the expected shape") from None
    if expires < time.time():
        raise Unknown("the Claude Code login has expired; opening Claude Code once refreshes it")
    return token


def _safe_iso(v) -> str | None:
    """An ISO timestamp the rest of the script can parse, or None."""
    if not isinstance(v, str):
        return None
    try:
        _ts(v)
    except ValueError:
        return None
    return v


def _percent(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _scope_name(scope) -> str | None:
    if not isinstance(scope, dict):
        return None
    for key in ("model", "surface"):
        v = scope.get(key)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, dict):
            for k in ("display_name", "name", "id"):
                if isinstance(v.get(k), str) and v[k]:
                    return v[k]
    return None


def claude_scoped(d: dict) -> list[dict]:
    """The usage page's scoped limits (one model's or surface's allowance): every `limits` entry
    with a named scope, then `seven_day_<model>` windows not already listed. Anything malformed
    is left out, so a page without them reads as before."""
    out = []
    limits = d.get("limits")
    for e in limits if isinstance(limits, list) else ():
        if not isinstance(e, dict):
            continue
        name, percent = _scope_name(e.get("scope")), _percent(e.get("percent"))
        if name is None or percent is None:
            continue
        group = e.get("group") if isinstance(e.get("group"), str) and e.get("group") else "limit"
        out.append({"name": name, "group": group, "percent": percent,
                    "resets_at": _safe_iso(e.get("resets_at")), "binding": e.get("is_active") is True})
    seen = {s["name"].lower() for s in out}
    for key, name in (("seven_day_opus", "Opus"), ("seven_day_sonnet", "Sonnet")):
        w = d.get(key)
        percent = _percent(w.get("utilization")) if isinstance(w, dict) else None
        if percent is not None and name.lower() not in seen:
            out.append({"name": name, "group": "weekly", "percent": percent,
                        "resets_at": _safe_iso(w.get("resets_at")), "binding": False})
    return out


def read_claude() -> Reading:
    req = urllib.request.Request(CLAUDE_URL, headers={"Authorization": f"Bearer {_claude_token()}",
                                                      "anthropic-beta": "oauth-2025-04-20"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise Unknown(f"usage page: {e}") from None
    try:
        five = d["five_hour"]                                 # null on a plan with no 5-hour window
        return Reading(
            provider="claude",
            at=time.time(),
            five_hour=float(five["utilization"]) if five else None,
            five_reset=five.get("resets_at") if five else None,
            week=float(d["seven_day"]["utilization"]),
            week_reset=d["seven_day"].get("resets_at"),
            week_start=(d.get("seven_day_breakdown") or {}).get("window_started_at"),
            overflow_billed=bool((d.get("extra_usage") or {}).get("is_enabled")),
            scoped=claude_scoped(d),
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


# ---- Antigravity --------------------------------------------------------------------------

AGY_TIMEOUT = 30


def _agy_json(text: str) -> dict | None:
    """Parse an `agy --output-format json` envelope, tolerating leading log/error lines."""
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    for line in reversed(text.splitlines()):
        s = line.strip()
        if s.startswith("{"):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return obj
            except ValueError:
                continue
    return None


def _agy_command(command: str) -> dict:
    """Run one zero-token `agy --print /<cmd> --output-format json` call.

    When `agy` is not signed in, it prints an authentication prompt to stderr and waits
    60 seconds for an OAuth callback even with stdin closed; watching stderr lets us
    abort immediately instead of hanging until timeout.
    """
    exe = shutil.which("agy")
    if exe is None:
        raise Unknown("the agy CLI isn't installed")
    try:
        p = subprocess.Popen(
            [exe, "--print", command, "--output-format", "json"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as e:
        raise Unknown(f"could not start agy: {e}") from None

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    auth_required = threading.Event()

    def read_stdout() -> None:
        assert p.stdout is not None
        stdout_chunks.append(p.stdout.read())

    def read_stderr() -> None:
        assert p.stderr is not None
        for line in p.stderr:
            stderr_chunks.append(line)
            if "authentication required" in line.lower() or "please sign in" in line.lower():
                auth_required.set()
                try:
                    p.kill()
                except OSError:
                    pass

    t_out = threading.Thread(target=read_stdout, daemon=True)
    t_err = threading.Thread(target=read_stderr, daemon=True)
    t_out.start()
    t_err.start()
    try:
        p.wait(timeout=AGY_TIMEOUT)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        t_out.join(timeout=2)
        t_err.join(timeout=2)
        raise Unknown(f"agy {command} didn't answer within {AGY_TIMEOUT}s") from None
    t_out.join(timeout=2)
    t_err.join(timeout=2)

    if auth_required.is_set():
        raise Unknown("Antigravity isn't signed in; run `agy` to log in")

    out = "".join(stdout_chunks)
    err = "".join(stderr_chunks).strip()
    env = _agy_json(out)
    if env is None:
        detail = err.splitlines()[-1] if err else f"exit code {p.returncode}"
        raise Unknown(f"agy {command}: {detail}")
    if env.get("status") != "SUCCESS":
        msg = env.get("error") or (err.splitlines()[-1] if err else f"status {env.get('status')}")
        raise Unknown(f"agy {command}: {msg}")
    data = (env.get("command") or {}).get("data")
    if not isinstance(data, dict):
        raise Unknown(f"agy {command} returned an unexpected shape")
    return data


def _agy_reset(v) -> str | None:
    """An active ISO reset timestamp, or None for missing/invalid/epoch sentinels."""
    iso = _safe_iso(v)
    if iso is None:
        return None
    ts = _ts(iso)
    return iso if ts is not None and ts > 0 else None


def _agy_used_percent(bucket: dict, reset: str | None) -> float | None:
    """Convert Antigravity's remaining_fraction (0..1) to percent used (0..100).

    Proto3 JSON serialization omits remaining_fraction when it is 0.0; when reset_time
    is active and remaining_fraction is omitted, the bucket is exhausted (100% used).
    """
    frac = _percent(bucket.get("remaining_fraction"))
    if frac is None:
        if "remaining_fraction" not in bucket and reset is not None:
            return 100.0
        return None
    clamped = max(0.0, min(1.0, frac))
    return round((1.0 - clamped) * 100.0, 2)


def _agy_window_kind(bucket: dict) -> str:
    w = bucket.get("window")
    if isinstance(w, str) and w:
        wl = w.lower()
        if wl in ("5h", "five_hour"):
            return "5h"
        if wl in ("weekly", "7d", "seven_day"):
            return "weekly"
        return w
    bid = bucket.get("id")
    if isinstance(bid, str) and bid:
        bl = bid.lower()
        if bl.endswith("-5h"):
            return "5h"
        if bl.endswith("-weekly"):
            return "weekly"
        return bid
    return "limit"


def _agy_use_g1_credits_setting() -> bool | None:
    """Read explicit useG1Credits preference from ~/.gemini/antigravity-cli/settings.json, if set."""
    path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("useG1Credits"), bool):
        return data["useG1Credits"]
    return None


def _parse_agy_group(group: dict) -> dict | None:
    if not isinstance(group, dict):
        return None
    name = group.get("name")
    if not isinstance(name, str) or not name:
        return None
    buckets_raw = group.get("buckets")
    if not isinstance(buckets_raw, list):
        return None
    buckets = []
    ids = []
    for b in buckets_raw:
        if not isinstance(b, dict):
            continue
        reset = _agy_reset(b.get("reset_time"))
        used = _agy_used_percent(b, reset)
        if used is None:
            continue
        kind = _agy_window_kind(b)
        bid = b.get("id") if isinstance(b.get("id"), str) else ""
        ids.append(bid)
        buckets.append({"kind": kind, "percent": used, "resets_at": reset})
    if not buckets:
        return None
    return {"name": name, "ids": ids, "buckets": buckets}


def read_antigravity() -> Reading:
    data = _agy_command("/usage")
    groups_raw = data.get("groups")
    if not isinstance(groups_raw, list) or not groups_raw:
        raise Unknown("agy /usage reported no quota groups")
    groups = [g for raw in groups_raw if (g := _parse_agy_group(raw)) is not None]
    with_weekly = [g for g in groups if any(b["kind"] == "weekly" for b in g["buckets"])]
    if not with_weekly:
        raise Unknown("agy /usage reported no weekly quota bucket")

    # Prefer the Gemini group as the primary windows; other model pools appear under scoped.
    primary = next(
        (g for g in with_weekly
         if "gemini" in g["name"].lower() or any(i.lower().startswith("gemini-") for i in g["ids"])),
        with_weekly[0],
    )
    five = next((b for b in primary["buckets"] if b["kind"] == "5h"), None)
    week = next(b for b in primary["buckets"] if b["kind"] == "weekly")
    week_reset = week["resets_at"]
    week_ts = _ts(week_reset)

    scoped = []
    order = {"5h": 0, "weekly": 1}
    for g in groups:
        if g is primary:
            extra = [b for b in g["buckets"] if b is not five and b is not week]
        else:
            extra = sorted(g["buckets"], key=lambda b: order.get(b["kind"], 2))
        for b in extra:
            entry = {
                "name": g["name"],
                "group": b["kind"],
                "percent": b["percent"],
                "resets_at": b["resets_at"],
                "binding": False,
            }
            if b["kind"] == "weekly" and b["resets_at"] is not None:
                b_ts = _ts(b["resets_at"])
                if b_ts is not None:
                    entry["window_start"] = _iso(b_ts - 7 * 86400)
            scoped.append(entry)

    credits = None
    try:
        cdata = _agy_command("/credits")
        cval = _percent(cdata.get("remaining_credits"))
        if cval is not None:
            credits = cval
    except Unknown:
        pass

    use_g1 = _agy_use_g1_credits_setting()
    overflow_billed = bool(credits is not None and credits > 0 and use_g1 is not False)

    return Reading(
        provider="antigravity",
        at=time.time(),
        five_hour=five["percent"] if five is not None else None,
        five_reset=five["resets_at"] if five is not None else None,
        week=week["percent"],
        week_reset=week_reset,
        week_start=_iso(week_ts - 7 * 86400) if week_ts is not None else None,
        overflow_billed=overflow_billed,
        scoped=scoped,
        scope=primary["name"],
        credits=credits,
    )


READERS = {"claude": read_claude, "codex": read_codex, "antigravity": read_antigravity}


# ---- assessment ---------------------------------------------------------------------------

def record(r: Reading) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**asdict(r), "pid": os.getpid()}) + "\n")


def _ts(iso: str | None) -> float | None:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() if iso else None


def local(iso: str | None) -> str:
    if not iso:
        return "unknown"
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    return t.strftime("%H:%M today") if t.date() == datetime.now().date() else t.strftime("%a %m-%d %H:%M")


def assess(r: Reading) -> dict:
    """Facts derived from a reading: time left, pace across the weekly window, and where it lands."""
    reset, start = _ts(r.week_reset), _ts(r.week_start)
    if start is None and reset is not None:
        start = reset - 7 * 86400
    hours_left, pace, projected = _pace(r.week, r.at, reset, start)
    scoped = []
    for s in r.scoped:
        s_reset = _ts(s["resets_at"])
        # A scoped window's start is known when carried explicitly (e.g. an independent weekly pool)
        # or when it resets with the primary weekly window.
        s_start = _ts(s.get("window_start"))
        same = s_reset is not None and reset is not None and abs(s_reset - reset) <= SAME_RESET_S
        if s_start is None and same:
            s_start = start
        s_left, s_pace, s_proj = _pace(s["percent"], r.at, s_reset, s_start)
        scoped.append({**s, "unused": 100 - s["percent"], "hours_to_reset": s_left,
                       "window_start_known": s_start is not None,
                       "pace_points_per_hour": s_pace, "projected_at_reset": s_proj,
                       "projected_unused_at_reset": 100 - s_proj if s_proj is not None else None})
    return {
        "five_hour_unused": 100 - r.five_hour if r.five_hour is not None else None,
        "week_unused": 100 - r.week,
        "hours_to_five_hour_reset": max((_ts(r.five_reset) - r.at) / 3600, 0) if r.five_reset else None,
        "hours_to_weekly_reset": hours_left,
        "weekly_pace_points_per_hour": pace,
        "projected_week_at_reset": projected,
        "projected_unused_at_reset": 100 - projected if projected is not None else None,
        "scoped": scoped,
    }


def _pace(used: float, at: float, reset: float | None, start: float | None):
    """Hours to the reset, points/hour so far, and the projected use at the reset."""
    hours_left = max((reset - at) / 3600, 0) if reset else None
    elapsed_h = (at - start) / 3600 if start else None
    pace = used / elapsed_h if elapsed_h and elapsed_h >= MIN_ELAPSED_H else None
    projected = min(used + pace * hours_left, 100.0) if pace is not None and hours_left is not None else None
    return hours_left, pace, projected


def show(r: Reading, a: dict) -> str:
    f = lambda v, fmt: "?" if v is None else format(v, fmt)
    def reset_text(used: float, resets_at: str | None, hours: float | None, fmt: str) -> str:
        if resets_at is None and used == 0:
            return "window not started"
        return f"resets {local(resets_at)} ({f(hours, fmt)}h)"

    qual = ", ".join(q for q in (r.plan, r.scope) if q)
    title = r.provider.capitalize() + (f" ({qual})" if qual else "")
    five = ("  5-hour window   none on this plan" if r.five_hour is None else
            f"  5-hour window  {r.five_hour:5.0f}% used   "
            f"{reset_text(r.five_hour, r.five_reset, a['hours_to_five_hour_reset'], '.1f')}")
    lines = [
        title,
        five,
        f"  weekly window  {r.week:5.0f}% used   "
        f"{reset_text(r.week, r.week_reset, a['hours_to_weekly_reset'], '.0f')}",
        f"  weekly pace    {f(a['weekly_pace_points_per_hour'], '.2f')} points/hour; at that pace "
        f"{f(a['projected_week_at_reset'], '.0f')}% used by the reset, "
        f"{f(a['projected_unused_at_reset'], '.0f')} points unused",
    ]
    for s in a.get("scoped", ()):
        label = f"{s['name']} {s['group']}"
        hours_fmt = ".1f" if s["group"] == "5h" else ".0f"
        lines.append(f"  {label:<15}{s['percent']:5.0f}% used   "
                     f"{reset_text(s['percent'], s['resets_at'], s['hours_to_reset'], hours_fmt)}"
                     + ("  \u2190 binding" if s["binding"] else ""))
        if s["window_start_known"]:
            lines.append(f"  {s['name'] + ' pace':<15}{f(s['pace_points_per_hour'], '.2f')} points/hour; at that pace "
                         f"{f(s['projected_at_reset'], '.0f')}% used by the reset, "
                         f"{f(s['projected_unused_at_reset'], '.0f')} points unused")
    lines += [
        f"  overflow       {'billed past 100%' if r.overflow_billed else 'refused past 100% (no billing)'}",
    ]
    if r.credits is not None:
        credits_text = str(int(r.credits)) if float(r.credits).is_integer() else f"{r.credits:g}"
        lines.append(f"  credits        {credits_text} remaining")
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
