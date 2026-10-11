#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "yt-dlp[default]",
#     "mlx-whisper; sys_platform == 'darwin' and platform_machine == 'arm64'",
#     "faster-whisper; sys_platform != 'darwin'",
#     "av<19; sys_platform != 'darwin'",  # faster-whisper 1.2.1 passes metadata_errors, which av 19 removed
# ]
# ///
"""Fetch a YouTube video's transcript as timestamped markdown.

Extracted from the video-reading recipe in a private project:
  1. Pull captions with yt-dlp as json3 (vtt rate-limits more often). Human captions are
     preferred over auto-captions; a 429 gets one retry after a pause.
  2. If no captions come back, transcribe the audio with Whisper instead: mlx-whisper on Apple
     Silicon, faster-whisper (CPU, int8) elsewhere.
  3. Group text into ~18s timestamped blocks and write transcript.md with a header recording
     the source, the engine, and the blind spots (auto-captions mangle proper nouns; no frames
     were read).

Usage:
  uv run --script yt_transcript.py <url> [<url> ...] [--out DIR] [--whisper auto|never|always]

uv builds and caches the script's environment from the header above. YouTube breaks old yt-dlp
releases often; when downloads start failing, refresh it with:
  uv run --upgrade-package yt-dlp --script yt_transcript.py <url>

Output lands in <out>/<video-id>/transcript.md
(default out: ${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/youtube).
The audio file used for Whisper is deleted afterwards; metadata.json is kept.

Environment:
  YT_WHISPER_MODEL   default: mlx-community/whisper-large-v3-turbo (mlx-whisper),
                     large-v3-turbo (faster-whisper)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
DEFAULT_OUT = CACHE / "rickdiculousli-tools" / "youtube"
DEFAULT_MODELS = {"mlx_whisper": "mlx-community/whisper-large-v3-turbo", "faster_whisper": "large-v3-turbo"}
BLOCK_SECONDS = 18


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def yt_dlp(*args: str) -> subprocess.CompletedProcess:
    """Run the yt-dlp pinned in this script's environment, not whatever is on PATH."""
    return run([sys.executable, "-m", "yt_dlp", "--no-warnings", *args])


def fetch_metadata(url: str) -> dict:
    p = yt_dlp("--skip-download", "--dump-json", url)
    if p.returncode != 0:
        sys.exit(f"yt-dlp metadata failed for {url}:\n{p.stderr.strip()}\n"
                 "If YouTube changed something, retry with: uv run --upgrade-package yt-dlp ...")
    return json.loads(p.stdout.splitlines()[0])


def fetch_captions(url: str, workdir: Path, lang: str, meta: dict) -> tuple[Path, str] | None:
    """Return (json3 path, kind) or None. Human captions first, then auto-captions."""
    attempts = []
    if lang in (meta.get("subtitles") or {}):
        attempts.append(("--write-sub", "human captions"))
    if lang in (meta.get("automatic_captions") or {}):
        attempts.append(("--write-auto-sub", "YouTube auto-captions"))
    for flag, kind in attempts:
        for attempt in range(2):
            for old in workdir.glob("vid*.json3"):
                old.unlink()
            p = yt_dlp(
                "--skip-download", flag, "--sub-lang", lang, "--sub-format", "json3",
                "-o", str(workdir / "vid.%(ext)s"), url,
            )
            found = sorted(workdir.glob("vid*.json3"))
            if found:
                return found[0], kind
            if "429" in p.stderr and attempt == 0:
                print("  captions rate-limited (429); retrying in 20s", file=sys.stderr)
                time.sleep(20)
                continue
            break
    return None


def json3_segments(path: Path) -> list[tuple[float, str]]:
    data = json.loads(path.read_text())
    segs = []
    for ev in data.get("events", []):
        if "segs" not in ev:
            continue
        text = "".join(s.get("utf8", "") for s in ev["segs"]).replace("\n", " ").strip()
        if text:
            segs.append((ev.get("tStartMs", 0) / 1000, text))
    return segs


def whisper_backend() -> str:
    """Whichever Whisper the script's environment installed for this platform."""
    for name in DEFAULT_MODELS:
        try:
            __import__(name)
        except ImportError:
            continue
        return name
    sys.exit("no Whisper backend installed (mlx-whisper or faster-whisper)")


def run_whisper(backend: str, model: str, audio: Path) -> list[tuple[float, str]]:
    if backend == "mlx_whisper":
        import mlx_whisper

        segments = mlx_whisper.transcribe(str(audio), path_or_hf_repo=model)["segments"]
        pairs = [(s["start"], s["text"]) for s in segments]
    else:
        from faster_whisper import WhisperModel

        segments, _ = WhisperModel(model, device="cpu", compute_type="int8").transcribe(str(audio))
        pairs = [(s.start, s.text) for s in segments]
    return [(float(start), text.strip()) for start, text in pairs if text.strip()]


def whisper_segments(url: str, workdir: Path, backend: str, model: str) -> list[tuple[float, str]]:
    for old in workdir.glob("audio.*"):
        old.unlink()
    p = yt_dlp("-f", "bestaudio/b", "-o", str(workdir / "audio.%(ext)s"), url)
    audio = next((a for a in workdir.glob("audio.*") if a.suffix not in (".part", ".ytdl")), None)
    if audio is None:
        sys.exit(f"audio download failed:\n{p.stderr.strip()}")
    print(f"  transcribing with {backend} {model} (this takes a while)", file=sys.stderr)
    try:
        return run_whisper(backend, model, audio)
    finally:
        audio.unlink(missing_ok=True)


def stamp(seconds: float) -> str:
    s = int(seconds)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def to_blocks(segs: list[tuple[float, str]]) -> list[str]:
    blocks, start, words = [], None, []
    for t, text in segs:
        if start is None:
            start = t
        elif t - start >= BLOCK_SECONDS:
            blocks.append(f"[{stamp(start)}] " + " ".join(words))
            start, words = t, []
        words.append(text)
    if words:
        blocks.append(f"[{stamp(start)}] " + " ".join(words))
    return [re.sub(r"\s+", " ", b) for b in blocks]


def transcribe(url: str, out_root: Path, whisper: str, lang: str) -> Path:
    meta = fetch_metadata(url)
    vid = meta["id"]
    workdir = out_root / vid
    workdir.mkdir(parents=True, exist_ok=True)
    keep = ("id", "title", "channel", "uploader", "upload_date", "duration", "webpage_url", "description")
    (workdir / "metadata.json").write_text(json.dumps({k: meta.get(k) for k in keep}, indent=2))
    print(f"{vid}: {meta.get('title')}", file=sys.stderr)

    caps = None if whisper == "always" else fetch_captions(url, workdir, lang, meta)
    if caps:
        segs, engine = json3_segments(caps[0]), caps[1]
    elif whisper == "never":
        sys.exit(f"{vid}: no captions available and --whisper never")
    else:
        backend = whisper_backend()
        model = os.environ.get("YT_WHISPER_MODEL", DEFAULT_MODELS[backend])
        segs, engine = whisper_segments(url, workdir, backend, model), f"{backend} {model}, audio only"

    blind = ["no frames read, so on-screen charts, slides, lower-thirds and speaker names were not seen"]
    if "auto" in engine or "whisper" in engine:
        blind.append("machine transcription mangles proper nouns (tickers, names, companies); verify before relying on one")

    up = meta.get("upload_date") or ""
    published = f"{up[:4]}-{up[4:6]}-{up[6:]}" if len(up) == 8 else "unknown"
    blocks = to_blocks(segs)
    header = [
        f"# {meta.get('channel') or meta.get('uploader')} — \"{meta.get('title')}\"",
        "",
        f"- source: {meta.get('webpage_url') or url}",
        f"- published: {published} | runtime: {stamp(meta.get('duration') or 0)}",
        f"- engine: {engine}",
        f"- fetched: {date.today().isoformat()} | {len(blocks)} blocks, ~{sum(len(b.split()) for b in blocks)} words",
        *[f"- blind spot: {b}" for b in blind],
        "",
    ]
    path = workdir / "transcript.md"
    path.write_text("\n".join(header) + "\n" + "\n\n".join(blocks) + "\n")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--whisper", choices=["auto", "never", "always"], default="auto",
                    help="auto: only when no captions exist (default)")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()
    for url in args.urls:
        print(transcribe(url, args.out, args.whisper, args.lang))


if __name__ == "__main__":
    main()
