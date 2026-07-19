# discord-video-downloader-bot

Paste a video link in Discord. The bot pulls the file with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and re-uploads it as a normal attachment so everyone can scrub and replay without opening TikTok / Reels / X / etc.

Built for self-hosting on a VPS or home box. No cloud account required beyond Discord.

## What it does

1. Watches messages for links  
2. Downloads the media (temp dir only)  
3. Shrinks the file with ffmpeg if it’s over Discord’s size limit  
4. Posts the video, tags who shared it, optional title  
5. Deletes the original link message (servers) and wipes temp files  

Works well with TikTok, Instagram, Facebook, X/Twitter, Reddit, Twitch clips, YouTube Shorts, and a lot of other sites yt-dlp supports. There’s also a fallback path for many “sensitive” X posts that plain yt-dlp chokes on.

**Not supported:** Group DMs or DMs between two people. Discord doesn’t let bots in there. Use a server (even a private one with just your friends).

## Requirements

- Python 3.11+ (3.12 is what we run in Docker)
- ffmpeg + ffprobe
- A Discord bot application with **Message Content Intent** turned on
- Bot permissions: View Channel, Send Messages, Attach Files, Manage Messages, Read Message History

## Install

```bash
git clone https://github.com/The-Khan-Labs/discord-video-downloader-bot.git
cd discord-video-downloader-bot

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
```

Put your token in `.env`:

```env
DISCORD_TOKEN=...
```

Then:

```bash
python main.py
```

Invite the bot (swap in your application client id):

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

There’s a unit template in `deploy/discord-video-bot.service`. Edit the paths, install it, `enable --now`. Prefer that over a raw `nohup` if this box reboots.

## Config

Everything is env vars — see `.env.example`.

| Var | Default | Notes |
|-----|---------|--------|
| `DISCORD_TOKEN` | — | required |
| `MAX_FILE_SIZE_MB` | `25` | match your server’s boost tier if higher |
| `MAX_DOWNLOADS_PER_USER_PER_HOUR` | `10` | failed jobs don’t burn the quota |
| `INCLUDE_AUTHOR` | `true` | `@user` on the re-upload |
| `INCLUDE_TITLE` | `true` | title under the mention |
| `INCLUDE_SOURCE_URL` | `false` | original link in the caption |
| `ALLOW_GENERIC_URLS` | `true` | try non-listed hosts via yt-dlp |
| `EXTRA_DENY_HOSTS` | | hosts to never touch |
| `DELETE_ORIGINAL_MESSAGE` | `true` | server channels only |
| `COMPRESS_VIDEOS` | `true` | needs ffmpeg |
| `CONCURRENT_DOWNLOAD_LIMIT` | `3` | global parallel jobs |
| `ALLOWED_CHANNEL_IDS` / `IGNORED_CHANNEL_IDS` | | optional channel filters |

Upload size is intentionally a bit under `MAX_FILE_SIZE_MB`. Discord sometimes 413s files that are “technically under 25MB.”

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
Dockerfile / docker-compose.yml
```

## Commands

- `!videostatus` — current limits (needs Manage Server)

## Keeping it healthy

Sites break scrapers all the time. When downloads start failing for a platform you care about:

```bash
pip install -U yt-dlp
# or rebuild the Docker image
```

Other things that bite people:

| Symptom | Likely cause |
|---------|----------------|
| Bot connects then dies with privileged intents | Message Content Intent off in the developer portal |
| “Too large for Discord” | long clip; try a higher boost tier or leave compression on |
| X video missing | sensitive media; fallback APIs can fail too — retry later |
| Nothing happens on a link | channel not allowed, rate limit, or bot missing perms |
| Two bots answering | second process; we use a lock file under `TEMP_DIR` |

Temp media lives under `TEMP_DIR` (default `/tmp/discord-video-bot`) and is deleted after each job. Only the Discord message keeps the video.

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Security stuff: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) — The Khan Labs

You are responsible for how you run this (Discord ToS, copyright, etc.). The bot only does what you ask it to on your own server.
