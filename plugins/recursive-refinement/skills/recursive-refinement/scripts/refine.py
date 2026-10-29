#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""The weekly refinement pass's scheduler, conversation reader and session-start surfacer.

    uv run --script refine.py conversations <repo> [--days 7]   # the user's messages and the replies they read
    uv run --script refine.py run [--repo NAME] [--dry-run DIR]  # one pass per registered repo, under the weekly cap
    uv run --script refine.py ledger                             # this week's spend
    uv run --script refine.py surface <repo>                     # unseen notes and open specs, for a SessionStart hook
    uv run --script refine.py install [--load]                   # the launchd job (macOS) and the `recursive-refinement` shim

The registry of repos and the cap are user data, in
${XDG_CONFIG_HOME:-~/.config}/rickdiculousli-tools/recursive-refinement/repos.json. The spend ledger and
what each repo has surfaced live in ${XDG_STATE_HOME:-~/.local/state}/rickdiculousli-tools/recursive-refinement/.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

PLUGIN = "recursive-refinement"
SKILL = "/recursive-refinement:recursive-refinement"
DEFAULTS = {
    "weekly_cap_usd": 100.0,
    "pass_cap_usd": 40.0,
    "model": "opus",
    "permission_mode": "auto",
    "repos": [],
    # headless jobs and agent briefs, not the user: a session whose first message starts with one is skipped
    "agent_prompt_prefixes": ["Act as the", "Read your brief at", "You are executor", "You generate", "=== QUEUED"],
    # Saturday 04:00 (launchd weekday 6), with catch-ups; a pass already done this week is skipped
    "schedule": [{"Weekday": 6, "Hour": 4, "Minute": 0}, {"Weekday": 0, "Hour": 9, "Minute": 30},
                 {"Weekday": 1, "Hour": 19, "Minute": 30}],
}
REMINDER = ("You can refine this weekly pass too: say what it should stop touching, to be bolder, "
            "or to pause, in any session.")
TAG = re.compile(r"<(system-reminder|task-notification|local-command-[a-z]+|command-[a-z]+)>.*?</\1>", re.S)


# ---- places --------------------------------------------------------------------------------

def _root(kind: str) -> Path:
    """XDG state/cache/config root for this plugin; empty or relative XDG values count as unset."""
    var, default = {"state": ("XDG_STATE_HOME", ".local/state"), "cache": ("XDG_CACHE_HOME", ".cache"),
                    "config": ("XDG_CONFIG_HOME", ".config")}[kind]
    value = os.environ.get(var, "")
    if value and Path(value).is_absolute():
        return Path(value) / "rickdiculousli-tools" / PLUGIN
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        base = Path(local) if local and Path(local).is_absolute() else Path.home() / "AppData" / "Local"
        return base / "rickdiculousli-tools" / PLUGIN / kind
    return Path.home() / default / "rickdiculousli-tools" / PLUGIN


def _path(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def load_config() -> dict:
    f = _root("config") / "repos.json"
    conf = dict(DEFAULTS)
    if f.exists():
        conf.update(json.loads(f.read_text(encoding="utf-8")))
    return conf


def find_repo(conf: dict, repo: str) -> dict:
    """The registry entry for a repo path or name; an unregistered path gets an empty entry."""
    for r in conf["repos"]:
        if _path(r["path"]) == _path(repo) or Path(r["path"]).name == repo:
            return r
    return {"path": str(_path(repo))}


def repo_key(path: Path) -> str:
    common = subprocess.run(["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True).stdout.strip() or str(path)
    canon = os.path.normcase(str(Path(common).resolve()))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


@contextlib.contextmanager
def state_lock():
    """The plugin's fixed root lock; a second run exits instead of waiting."""
    root = _root("state")
    try:
        root.mkdir(parents=True, exist_ok=True)
        fh = open(root / "state.lock", "a+")
    except OSError as e:
        sys.exit(f"recursive-refinement: state dir {root} is not writable ({e}); set XDG_STATE_HOME")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("recursive-refinement: another run holds the lock")
    try:
        yield root
    finally:
        fh.close()


# ---- conversations -------------------------------------------------------------------------

def slug(path: str) -> str:
    """Claude Code's project folder name for a path; `*` survives so a glob stays a glob."""
    return re.sub(r"[^A-Za-z0-9*]", "-", path)


def session_dirs(entry: dict, projects: Path) -> list[Path]:
    patterns = [slug(str(_path(entry["path"])))]
    for g in entry.get("session_paths", []):
        expanded = os.path.expanduser(g)
        patterns.append(slug(expanded if "*" in expanded else str(_path(expanded))))
    if not projects.is_dir():
        return []
    return sorted(d for d in projects.iterdir() if d.is_dir() and any(fnmatch.fnmatchcase(d.name, p) for p in patterns))


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def _human(rec: dict) -> str | None:
    """What the user typed in a record, or None when the record is a tool result, a hook or a command echo."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
        return None
    content = rec.get("message", {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    text = TAG.sub("", _text(content)).strip()
    if not text or text.startswith(("[Request interrupted", "Caveat:", "<")):
        return None
    return text


def read_session(f: Path, since: dt.datetime, prefixes: list[str]) -> list[dict]:
    """Turns since `since`: each is the user's message and the last advisor text before their next one."""
    turns: list[dict] = []
    first = True
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("entrypoint") == "sdk-cli":   # headless `claude -p` jobs: filers, passes, namers
                return []
            text = _human(rec)
            if text is not None:
                if first and text.startswith(tuple(prefixes)):
                    return []
                first = False
                ts = rec.get("timestamp", "")
                try:
                    at = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                turns.append({"at": at, "user": text, "reply": ""})
            elif rec.get("type") == "assistant" and turns and not rec.get("isSidechain"):
                reply = _text(rec.get("message", {}).get("content", [])).strip()
                if reply:
                    turns[-1]["reply"] = reply
    return [t for t in turns if t["at"] >= since]


def _cut(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + f" […{len(s) - n} more chars]"


def conversations(repo: str, days: float, max_user: int, max_reply: int, max_total: int, session: str | None,
                  conf: dict | None = None, projects: Path | None = None) -> str:
    conf = conf or load_config()
    projects = projects or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    out, total, skipped = [], 0, 0
    files = [f for d in session_dirs(find_repo(conf, repo), projects) for f in d.glob("*.jsonl")
             if dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc) >= since
             and (session is None or f.stem.startswith(session))]
    sessions = [(f, read_session(f, since, conf["agent_prompt_prefixes"])) for f in files]
    sessions = sorted(((f, t) for f, t in sessions if t), key=lambda x: x[1][0]["at"])
    turns_n = sum(len(t) for _, t in sessions)
    out.append(f"# {len(sessions)} sessions, {turns_n} messages since {since:%Y-%m-%d}")
    for f, turns in sessions:
        block = [f"\n## {turns[0]['at']:%Y-%m-%d} session {f.stem[:8]} ({len(turns)} messages)"]
        for t in turns:
            block.append(f"- **user** {t['at']:%m-%d %H:%M}: {_cut(t['user'], max_user)}")
            if t["reply"] and max_reply:
                block.append(f"  - reply: {_cut(t['reply'], max_reply)}")
        text = "\n".join(block)
        if session is None and total + len(text) > max_total:
            skipped += 1
            continue
        out.append(text)
        total += len(text)
    if skipped:
        out.append(f"\n({skipped} sessions left out at the size cap; read one with --session <id>)")
    return "\n".join(out)


# ---- the weekly run ------------------------------------------------------------------------

def week(now: dt.datetime | None = None) -> str:
    d = (now or dt.datetime.now()).date()   # a week starts on Saturday, so its Sunday and Monday catch-ups fall in it
    return (d - dt.timedelta(days=(d.weekday() - 5) % 7)).isoformat()


def ledger_rows(state: Path) -> list[dict]:
    f = state / "ledger.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


def spent(rows: list[dict], wk: str) -> float:
    return round(sum(r["cost_usd"] for r in rows if r["week"] == wk), 4)


def paused(repo: Path) -> bool:
    rules = repo / "docs" / "refinement" / "rules.md"
    return rules.exists() and re.search(r"(?mi)^paused:\s*(yes|true)\b", rules.read_text(encoding="utf-8")) is not None


def pass_command(conf: dict, repo: Path, cap: float, dry_run: Path | None) -> list[str]:
    mode = f"dry-run {dry_run / (repo.name + '.md')}" if dry_run else "land"
    settings = {"autoMode": {"allow": ["$defaults", (
        "The weekly refinement pass: editing files in the repo it was given and in its own worktrees, running "
        "that repo's checks, committing on a refinement branch, fast-forward merging it into the repo's default "
        "branch and pushing to origin, when the repo's docs/refinement/rules.md allows it.")]}}
    cmd = ["claude", "-p", f"{SKILL} repo={repo} mode={mode}", "--output-format", "json",
           "--max-budget-usd", f"{cap:.2f}", "--permission-mode", conf["permission_mode"],
           "--model", conf["model"], "--settings", json.dumps(settings), "--add-dir", str(repo),
           "--add-dir", str(_root("cache"))]
    if dry_run:
        cmd += ["--add-dir", str(dry_run)]
    return cmd


def run(conf: dict, only: str | None, dry_run: Path | None, runner=subprocess.run, pass_cap: float | None = None) -> int:
    with state_lock() as state:
        wk, rows = week(), ledger_rows(state)
        repos = [r for r in conf["repos"] if only is None or find_repo(conf, only) is r]
        if only and not repos:
            sys.exit(f"recursive-refinement: {only} is not registered in {_root('config') / 'repos.json'}")
        for entry in repos:
            repo = _path(entry["path"])
            left = conf["weekly_cap_usd"] - spent(rows, wk)
            if paused(repo):
                print(f"{repo.name}: paused in its rules; skipped")
                continue
            if not dry_run and only is None and any(r["week"] == wk and r["repo"] == repo.name and not r["dry_run"] and r["ok"]
                                   for r in rows):
                print(f"{repo.name}: already passed this week")   # catch-up times; --repo runs again
                continue
            if left < 1:
                print(f"{repo.name}: the weekly cap of ${conf['weekly_cap_usd']:.0f} is reached; stopping")
                break
            cap = min(left, pass_cap or conf["pass_cap_usd"])
            cwd = _root("cache") / "run" / repo.name   # outside the repo, so its hooks and filers never see the pass
            cwd.mkdir(parents=True, exist_ok=True)
            if dry_run:
                dry_run.mkdir(parents=True, exist_ok=True)
            started = dt.datetime.now().isoformat(timespec="seconds")
            proc = runner(pass_command(conf, repo, cap, dry_run), cwd=cwd, capture_output=True, text=True)
            try:
                result = json.loads(proc.stdout)
                cost, ok, said = float(result.get("total_cost_usd", cap)), not result.get("is_error"), result.get("result", "")
            except (json.JSONDecodeError, TypeError, ValueError):
                cost, ok, said = cap, False, (proc.stdout + proc.stderr)[-2000:]   # unknown cost counts as the whole cap
            row = {"week": wk, "repo": repo.name, "started": started, "dry_run": bool(dry_run),
                   "cost_usd": round(cost, 4), "ok": ok and proc.returncode == 0}
            rows.append(row)
            with open(state / "ledger.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            runs = state / "runs" / wk
            runs.mkdir(parents=True, exist_ok=True)
            (runs / f"{repo.name}{'-dry' if dry_run else ''}.md").write_text(said or "", encoding="utf-8")
            print(f"{repo.name}: {'ok' if row['ok'] else 'failed'}, ${cost:.2f}; "
                  f"week ${spent(rows, wk):.2f} of ${conf['weekly_cap_usd']:.0f}")
    return 0


# ---- session start -------------------------------------------------------------------------

def _frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return dict(re.findall(r"(?m)^(\w+):\s*(.*?)\s*$", m.group(1))) if m else {}


def surface(conf: dict, repo: str) -> str:
    """Unseen note lines and open specs for the repo and the repos it serves; marks the notes seen."""
    here = _path(repo)
    sources = [here] + [_path(r["path"]) for r in conf["repos"]
                        if any(_path(s) == here for s in r.get("surface_in", []))]
    state = _root("state")
    lines, needs = [], []
    for src in sources:
        base = src / "docs" / "refinement"
        if not base.is_dir():
            continue
        seen_file = state / repo_key(src) / "seen.json"
        seen = set(json.loads(seen_file.read_text())) if seen_file.exists() else set()
        notes = base / "notes.md"
        fresh = [l.strip() for l in (notes.read_text(encoding="utf-8").splitlines() if notes.exists() else [])
                 if l.startswith("- ")]
        new = [l for l in fresh if hashlib.sha256(l.encode()).hexdigest()[:16] not in seen]
        lines += [f"{l}" + (f" ({src.name})" if src != here else "") for l in new]
        for spec in sorted((base / "specs").glob("*.md")) if (base / "specs").is_dir() else []:
            text = spec.read_text(encoding="utf-8")
            if _frontmatter(text).get("status", "open") == "open":
                title = next((l[2:] for l in text.splitlines() if l.startswith("# ")), spec.stem)
                needs.append(f"- {title} ({spec})")
        if new:
            try:
                seen_file.parent.mkdir(parents=True, exist_ok=True)
                seen_file.write_text(json.dumps(sorted(seen | {hashlib.sha256(l.encode()).hexdigest()[:16]
                                                               for l in new})))
            except OSError:
                pass
    if not lines and not needs:
        return ""
    out = ["Weekly refinement (open your first reply with these, one line each, in plain words):"]
    if lines:
        out += ["Changed since the last session:"] + lines
    if needs:
        out += ["Needs you (the user answers yes, no or tell me more; set the spec's status to approved or rejected):"] + needs
    out.append(REMINDER)
    return "\n".join(out)


# ---- install -------------------------------------------------------------------------------

LABEL = "local.rickdiculousli-tools.recursive-refinement"


def plist(conf: dict, script: Path) -> str:
    log = _root("state") / "launchd.log"
    cmd = (f'export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"; '
           f"uv run --script {shlex.quote(str(script))} run")
    times = "\n".join("    <dict>" + "".join(f"<key>{k}</key><integer>{v}</integer>" for k, v in t.items()) + "</dict>"
                      for t in conf["schedule"])
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <!-- The weekly refinement pass. caffeinate keeps the Mac awake until it ends; a time missed while
       asleep fires on wake, and a repo already passed this week is skipped. -->
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-i</string>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>{esc(cmd)}</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
{times}
  </array>
  <key>StandardOutPath</key><string>{esc(str(log))}</string>
  <key>StandardErrorPath</key><string>{esc(str(log))}</string>
</dict>
</plist>
"""


def install(conf: dict, script: Path, load: bool) -> None:
    shim = Path.home() / ".local" / "bin" / "recursive-refinement"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text(f'#!/bin/sh\nexec uv run --quiet --script {shlex.quote(str(script))} "$@"\n')
    shim.chmod(0o755)
    print(f"shim: {shim} -> {script}")
    if sys.platform != "darwin":
        print("not macOS: no launchd job; run `recursive-refinement run` from cron or by hand")
        return
    agent = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    agent.write_text(plist(conf, script))
    print(f"launchd job: {agent} ({'loading' if load else 'not loaded'})")
    if load:
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(agent)], check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="recursive-refinement", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("conversations", help="the user's messages and the replies they read, for one repo")
    c.add_argument("repo")
    c.add_argument("--days", type=float, default=7)
    c.add_argument("--session", help="one session (id prefix), not cut at the size cap")
    c.add_argument("--max-user", type=int, default=1500)
    c.add_argument("--max-reply", type=int, default=600)
    c.add_argument("--max-total", type=int, default=60000)
    r = sub.add_parser("run", help="one pass per registered repo, under the weekly cap")
    r.add_argument("--repo")
    r.add_argument("--dry-run", type=Path, metavar="DIR", help="land nothing; write each repo's plan to DIR/<repo>.md")
    r.add_argument("--pass-cap", type=float, metavar="USD", help="this run's cap per pass, below the registry's")
    sub.add_parser("ledger", help="this week's spend")
    s = sub.add_parser("surface", help="unseen notes and open specs, for a SessionStart hook")
    s.add_argument("repo")
    i = sub.add_parser("install", help="the launchd job (not loaded unless --load) and the shim")
    i.add_argument("--load", action="store_true")
    a = ap.parse_args(argv)
    conf = load_config()
    if a.cmd == "conversations":
        print(conversations(a.repo, a.days, a.max_user, a.max_reply, a.max_total, a.session, conf))
    elif a.cmd == "run":
        return run(conf, a.repo, a.dry_run.resolve() if a.dry_run else None, pass_cap=a.pass_cap)
    elif a.cmd == "ledger":
        rows, wk = ledger_rows(_root("state")), week()
        for row in (x for x in rows if x["week"] == wk):
            print(f"{row['started']} {row['repo']}{' (dry run)' if row['dry_run'] else ''}: ${row['cost_usd']:.2f}")
        print(f"{wk}: ${spent(rows, wk):.2f} of ${conf['weekly_cap_usd']:.0f}")
    elif a.cmd == "surface":
        try:
            text = surface(conf, a.repo)
        except Exception:   # a session start never fails on this
            text = ""
        if text:
            print(text)
    elif a.cmd == "install":
        install(conf, Path(__file__).resolve(), a.load)
    return 0


if __name__ == "__main__":
    sys.exit(main())
