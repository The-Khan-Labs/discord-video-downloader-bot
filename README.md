# Discord Video Rehost Bot

Self-hosted Discord bot that watches for social video links, downloads them, and re-uploads the video as a **native Discord attachment** so people can play it without leaving the app.

## Features

- Detects links from TikTok, Instagram, Facebook, YouTube Shorts, X/Twitter, Reddit, Twitch clips, and Daily Mail videos
- Downloads with **yt-dlp** (Python API) plus an X/Twitter fallback for many sensitive posts
- Re-uploads as a normal Discord file (video only — no caption spam)
- Deletes the original link message in servers (when the bot has permission)
- Compresses oversized files with **ffmpeg** to fit Discord’s upload limit
- Per-user rate limits, concurrent download cap, temp files always cleaned up
- Config via environment variables
- Docker + systemd templates included

## Requirements

- Python **3.11+** (3.12 recommended; 3.13 needs extras in `requirements.txt`)
- **ffmpeg** + **ffprobe** on `PATH` (for compression)
- A Discord application/bot with:
  - **Message Content Intent** enabled
  - Permissions: View Channel, Send Messages, Attach Files, Manage Messages, Read Message History

## Quick start

```bash
git clone https://github.com/YOUR_USER/discord-video-bot.git
cd discord-video-bot

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env and set DISCORD_TOKEN=...

python main.py
```

Invite URL pattern:

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2147600448&scope=bot
```

## Configuration

See `.env.example`. Important variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | *(required)* | Bot token |
| `MAX_FILE_SIZE_MB` | `25` | Configured Discord size cap |
| `MAX_DOWNLOADS_PER_USER_PER_HOUR` | `10` | Per-user rate limit |
| `DOWNLOAD_TIMEOUT_SECONDS` | `120` | Download timeout |
| `COMPRESS_VIDEOS` | `true` | ffmpeg when over size budget |
| `ALLOWED_CHANNEL_IDS` | empty | If set, only these channels |
| `IGNORED_CHANNEL_IDS` | empty | Never process these |
| `DELETE_ORIGINAL_MESSAGE` | `true` | Delete link messages in servers |
| `CONCURRENT_DOWNLOAD_LIMIT` | `3` | Parallel downloads |

The bot uses a slightly lower **upload budget** than `MAX_FILE_SIZE_MB` so Discord is less likely to reject near-limit files.

## Project layout

```
main.py                     # Entry point, logging, single-instance lock
config.py                   # Env-based settings
cogs/video_downloader.py    # Message listener + re-upload
utils/download_handler.py   # yt-dlp, X fallback, compression
utils/file_manager.py       # Temp dirs (always deleted after use)
utils/validators.py         # Platform URL detection
utils/process_lock.py       # Prevent two bot processes
deploy/discord-video-bot.service
Dockerfile
docker-compose.yml
```

## Docker

```bash
cp .env.example .env
# set DISCORD_TOKEN

docker compose up -d --build
docker compose logs -f
```

## systemd

See `deploy/discord-video-bot.service`. Copy to `/etc/systemd/system/`, edit paths, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discord-video-bot
```

## Notes

- **Group DMs / friend-to-friend DMs:** Discord does not allow bots there. Use a server (or a private mini-server for friends).
- **Bot DMs:** Supported if the user shares a server with the bot and can message it.
- **Instagram / some Facebook posts** may need cookies or fail regionally — keep `yt-dlp` updated: `pip install -U yt-dlp`.
- Temp videos are deleted after upload; only Discord keeps the attachment.

## Admin command

- `!videostatus` — show limits (requires **Manage Server**)

## License

MIT — see [LICENSE](LICENSE).
