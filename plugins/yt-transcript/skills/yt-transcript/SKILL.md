---
name: yt-transcript
description: Use whenever you need to read, summarize, quote or check what is said in a YouTube video. Writes a timestamped transcript from captions, auto-captions or Whisper.
---

# YouTube transcript

Run the bundled script whenever you need to read a video, then read the transcript
it prints the path of:

```sh
uv run --script <skill-dir>/scripts/yt_transcript.py <url> [<url> ...]
```

It tries human captions first, then YouTube's auto-captions (json3, one retry after
an HTTP 429), and falls back to transcribing the audio with Whisper when captions are
missing or rate-limited: `mlx-whisper` on Apple Silicon, `faster-whisper` on CPU
elsewhere (slower, about 2 GB of RAM). It needs `ffmpeg` on PATH.

Flags:

- `--whisper auto|never|always`: `auto` (default) uses Whisper only without captions.
- `--lang <code>`: caption language, default `en`.
- `--out <dir>`: default `${XDG_CACHE_HOME:-~/.cache}/rickdiculousli-tools/youtube`.
  Output is `<out>/<video-id>/transcript.md` plus `metadata.json`.
- `YT_WHISPER_MODEL` overrides the Whisper model.

The transcript header records the source, engine and blind spots. Machine
transcripts mangle proper nouns, so verify any name, company or ticker before
relying on it. No frames are read: on-screen slides and charts are not seen.

If YouTube downloads start failing, refresh yt-dlp:
`uv run --upgrade-package yt-dlp --script <skill-dir>/scripts/yt_transcript.py <url>`.
