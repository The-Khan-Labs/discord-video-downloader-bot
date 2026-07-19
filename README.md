# Discord Video Rehost Bot

Self-hosted Discord bot that turns social (and other) video links into **native Discord attachments**.

Drop a link → bot downloads with **yt-dlp** → uploads the video file → cleans temp files.

## Features

- **yt-dlp powered** — works with the huge set of sites yt-dlp supports (TikTok, Instagram, Facebook, X/Twitter, Reddit, Twitch clips, YouTube Shorts, Daily Mail, and many more)
- **Generic URL mode** — any non-blocked `http(s)` link can be tried (disable if you only want known social hosts)
- **X/Twitter fallback** for many sensitive posts yt-dlp alone misses
- **Caption**: tags the person who shared + optional video title
- Deletes the original link message in servers (when permitted)
- Compresses oversized files with **ffmpeg** to fit Discord’s limit
- Per-user rate limits, concurrency cap, single-instance lock
- Temp videos **always deleted** after upload or failure
- Env-based config, Docker + systemd templates

## Open-source checklist

| Item | Status |
|------|--------|
| MIT License | `LICENSE` |
| README + setup | this file |
| `.env.example` (no secrets) | yes |
| `.gitignore` | blocks `.env`, venv, logs, media |
| Contributing guide | `CONTRIBUTING.md` |
| Security policy | `SECURITY.md` |
| Deploy templates | `Dockerfile`, `docker-compose.yml`, `deploy/*.service` |

## Requirements

- Python **3.11+** (3.12 recommended)
- **ffmpeg** + **ffprobe**
- Discord bot with **Message Content Intent**
- Permissions: View Channel, Send Messages, Attach Files, Manage Messages, Read History

## Quick start

```bash
git clone https://github.com/YOUR_USER/discord-video-bot.git
cd discord-video-bot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# set DISCORD_TOKEN=...

python main.py
```

Invite (replace client id):

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2147600448&scope=bot
```

## Configuration

See `.env.example`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | required | Bot token |
| `MAX_FILE_SIZE_MB` | `25` | Size cap (upload budget is slightly lower) |
| `MAX_DOWNLOADS_PER_USER_PER_HOUR` | `10` | Rate limit (failures refunded) |
| `INCLUDE_AUTHOR` | `true` | Mention who shared the link |
| `INCLUDE_TITLE` | `true` | Video title in caption |
| `INCLUDE_SOURCE_URL` | `false` | Original URL under the video |
| `ALLOW_GENERIC_URLS` | `true` | Try any non-denied URL via yt-dlp |
| `EXTRA_DENY_HOSTS` | empty | Comma-separated hosts to never try |
| `DELETE_ORIGINAL_MESSAGE` | `true` | Remove link messages in servers |
| `COMPRESS_VIDEOS` | `true` | ffmpeg when oversize |
| `CONCURRENT_DOWNLOAD_LIMIT` | `3` | Parallel jobs |

## Example caption

```
@alice
Funny cat compilation
```

(video attachment)

## Project layout

```
main.py
config.py
cogs/video_downloader.py
utils/download_handler.py   # yt-dlp + X API fallback + ffmpeg
utils/validators.py         # URL extract (known + generic)
utils/file_manager.py       # temp dirs, always cleaned
utils/process_lock.py
deploy/
Dockerfile
docker-compose.yml
```

## Docker

```bash
cp .env.example .env   # set token
docker compose up -d --build
```

## Notes

- **Group DMs / friend DMs:** Discord does not allow bots there — use a server.
- Keep **yt-dlp** updated: `pip install -U yt-dlp`
- Long YouTube videos may exceed size limits even after compress
- Some Instagram/Facebook posts need cookies or are region-locked

## Admin

`!videostatus` — limits overview (Manage Server)

## License

MIT — see [LICENSE](LICENSE).
