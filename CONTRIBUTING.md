# Contributing

If you’re fixing a site, a crash, or docs: thanks.

## Dev setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# DISCORD_TOKEN in .env for local runs — never commit it
```

You’ll want ffmpeg installed if you’re testing compression.

## Before you open a PR

- Keep changes focused.
- Don’t commit `.env`, tokens, or downloaded media.
- Temp files should still get deleted after success/failure.
- Prefer fixing via yt-dlp upgrades over hardcoding one-off site parsers, unless yt-dlp is truly blocked (see the X fallback for that pattern).

Quick sanity check:

```bash
python -m py_compile main.py config.py cogs/*.py utils/*.py
```

## Bugs

Open an issue with:

- a sample URL if you can share one
- relevant log lines (token redacted)
- `python --version` and `yt-dlp --version`
