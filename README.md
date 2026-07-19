# discord-video-downloader-bot

Paste a video link in Discord → bot re-uploads it as a native attachment.

Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp). Self-hosted.

## Requirements

- Python 3.11+
- ffmpeg
- Discord bot + **Message Content Intent**
- Perms: Send Messages, Attach Files, Manage Messages

## Setup

```bash
git clone https://github.com/The-Khan-Labs/discord-video-downloader-bot.git
cd discord-video-downloader-bot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# set DISCORD_TOKEN

python main.py
```

Invite:

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2147600448&scope=bot
```

Docker:

```bash
cp .env.example .env
docker compose up -d --build
```

## Config

See `.env.example`. Important ones:

| Var | Default |
|-----|---------|
| `DISCORD_TOKEN` | required |
| `MAX_FILE_SIZE_MB` | `25` |
| `MAX_DOWNLOADS_PER_USER_PER_HOUR` | `10` |
| `INCLUDE_AUTHOR` | `true` |
| `INCLUDE_TITLE` | `true` |
| `DELETE_ORIGINAL_MESSAGE` | `true` |
| `COMPRESS_VIDEOS` | `true` |

## Notes

- Update yt-dlp when sites break: `pip install -U yt-dlp`
- Temp files are deleted after each job

## License

[MIT](LICENSE) — The Khan Labs
