# discord-video-downloader-bot

Paste a video link in Discord. The bot downloads it with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and re-uploads it as a normal attachment so people can play it in-app.

Self-hosted. No extra cloud service beyond Discord.

## What it does

1. Watches messages for video links  
2. Downloads the media (temp dir only)  
3. Compresses with ffmpeg if it’s over Discord’s size limit  
4. Posts the video, tags who shared it, optional title  
5. Deletes the original link message and wipes temp files  

Works with TikTok, Instagram, Facebook, X/Twitter, Reddit, Twitch clips, YouTube Shorts, and most other sites yt-dlp supports. There’s a fallback for many sensitive X posts that plain yt-dlp can’t get.

## Requirements

- Python 3.11+ (3.12 in Docker)
- ffmpeg + ffprobe
- Discord bot with **Message Content Intent** enabled
- Permissions: View Channel, Send Messages, Attach Files, Manage Messages, Read Message History

## Setup

```bash
git clone https://github.com/The-Khan-Labs/discord-video-downloader-bot.git
cd discord-video-downloader-bot

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
```

Set your token:

```env
DISCORD_TOKEN=...
```

Run:

```bash
python main.py
```

Invite (replace client id):

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2147600448&scope=bot
```

### Docker

```bash
cp .env.example .env   # set DISCORD_TOKEN
docker compose up -d --build
docker compose logs -f
```

### systemd

Unit template: `deploy/discord-video-bot.service`. Edit paths, then `enable --now`. Better than bare `nohup` across reboots.

## Config

All settings are env vars — full list in `.env.example`.

| Var | Default | Notes |
|-----|---------|--------|
| `DISCORD_TOKEN` | — | required |
| `MAX_FILE_SIZE_MB` | `25` | raise if your server has a higher boost tier |
| `MAX_DOWNLOADS_PER_USER_PER_HOUR` | `10` | failed jobs don’t count |
| `INCLUDE_AUTHOR` | `true` | `@user` on the re-upload |
| `INCLUDE_TITLE` | `true` | video title under the mention |
| `INCLUDE_SOURCE_URL` | `false` | original URL in the caption |
| `ALLOW_GENERIC_URLS` | `true` | try non-listed hosts via yt-dlp |
| `EXTRA_DENY_HOSTS` | | comma-separated hosts to skip |
| `DELETE_ORIGINAL_MESSAGE` | `true` | remove the link message after posting |
| `COMPRESS_VIDEOS` | `true` | needs ffmpeg |
| `CONCURRENT_DOWNLOAD_LIMIT` | `3` | parallel downloads |
| `ALLOWED_CHANNEL_IDS` | | empty = all channels |
| `IGNORED_CHANNEL_IDS` | | never process these |
| `DOWNLOAD_TIMEOUT_SECONDS` | `180` | download timeout |
| `TEMP_DIR` | `/tmp/discord-video-bot` | temp downloads |
| `LOG_FILE` | `logs/bot.log` | rotating log |

Upload budget is slightly under `MAX_FILE_SIZE_MB` so Discord is less likely to reject near-limit files.

## Example

```
@alice
Funny cat compilation
```
*(+ video attachment)*

## Layout

```
main.py                     entrypoint, logging, process lock
config.py                   env → settings
cogs/video_downloader.py    message handler, rate limit, upload
utils/download_handler.py   yt-dlp, X fallback, ffmpeg
utils/validators.py         URL parsing
utils/file_manager.py       temp dirs (always removed)
utils/process_lock.py       one instance only
deploy/                     systemd unit
Dockerfile
docker-compose.yml
```

## Commands

- `!videostatus` — current limits (Manage Server)

## Maintenance

Sites change often. When a platform stops working:

```bash
pip install -U yt-dlp
# or rebuild Docker
```

Temp files live under `TEMP_DIR` and are deleted after every job. Only Discord keeps the uploaded video.

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Security: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) — The Khan Labs
