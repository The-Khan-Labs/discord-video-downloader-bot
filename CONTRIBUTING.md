# Contributing

Thanks for helping improve this project.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# set DISCORD_TOKEN for local testing only — never commit .env
```

Install **ffmpeg** for compression.

## Guidelines

- Keep secrets out of git (`.env` is gitignored).
- Prefer small, focused PRs.
- Match existing style (async, type hints, short user-facing messages).
- Temp media must always be deleted after upload or failure.
- Don’t add hard-coded site support when yt-dlp already handles it — prefer generic URL mode + denylist.

## Useful commands

```bash
python -m py_compile main.py config.py cogs/*.py utils/*.py
python main.py
```

## Reporting bugs

Open an issue with:

1. Platform / example URL (if public)
2. Bot log lines (redact tokens)
3. Python version, OS, yt-dlp version (`yt-dlp --version`)
