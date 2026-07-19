# discord-video-downloader-bot

Paste a video link in your Discord server. The bot downloads it and posts the actual video file so people can watch it inside Discord — no opening TikTok, Reels, X, etc.

You run this on **your own computer or server**. Free and open source ([MIT](LICENSE)).

## What you get

1. Someone posts a video link  
2. Bot downloads it  
3. If the file is too big for Discord, it shrinks it  
4. Bot posts the video (tags who shared it + title)  
5. Original link message is removed; temporary files are deleted  

Works with **TikTok, Instagram, Facebook, X/Twitter, Reddit, Twitch clips, YouTube Shorts**, and many other sites.

---

## Before you start

You need:

| Need | Why |
|------|-----|
| A computer or VPS that stays online | The bot has to run somewhere |
| [Python 3.11+](https://www.python.org/downloads/) | Runs the bot |
| [ffmpeg](https://ffmpeg.org/download.html) | Shrinks large videos |
| A free Discord account | Create the bot app |

**Install ffmpeg (pick your system):**

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y ffmpeg

# macOS (Homebrew)
brew install ffmpeg

# Windows: install from https://ffmpeg.org/download.html and add it to PATH
```

Check Python:

```bash
python3 --version
# should say 3.11 or higher
```

---

## 1. Create the Discord bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and sign in  
2. **New Application** → give it a name → Create  
3. Left sidebar → **Bot** → **Add Bot** (or Reset Token if it already exists)  
4. Under **Token**, click **Reset Token** / **Copy** — save this somewhere private  
5. On the same Bot page, scroll to **Privileged Gateway Intents**  
6. Turn **ON**: **Message Content Intent** → Save  

Without Message Content Intent, the bot cannot read links people post.

---

## 2. Invite it to your server

1. In the Developer Portal → your app → **OAuth2** → **URL Generator**  
2. Scopes: check **bot**  
3. Bot permissions: check  
   - View Channels  
   - Send Messages  
   - Attach Files  
   - Manage Messages  
   - Read Message History  
4. Copy the URL at the bottom, open it in a browser, pick your server, authorize  

Or use this link (replace `YOUR_CLIENT_ID` with the **Application ID** on the General Information page):

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2147600448&scope=bot
```

---

## 3. Install and run the bot

```bash
git clone https://github.com/The-Khan-Labs/discord-video-downloader-bot.git
cd discord-video-downloader-bot

python3 -m venv .venv

# Mac / Linux
source .venv/bin/activate

# Windows
# .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
```

Open the `.env` file in a text editor and set your token:

```env
DISCORD_TOKEN=paste_your_bot_token_here
```

Start it:

```bash
python main.py
```

You should see a log line like `Logged in as ...`. Leave that terminal open while you use the bot.

**Test:** in a server channel the bot can see, paste a TikTok or YouTube Shorts link. The bot should post the video file.

---

## Optional: Docker

If you prefer Docker:

```bash
cp .env.example .env
# put DISCORD_TOKEN in .env

docker compose up -d --build
docker compose logs -f
```

---

## Optional: keep it running on a Linux server

A systemd example is in `deploy/discord-video-bot.service`.  
Copy it, fix the paths, then:

```bash
sudo systemctl enable --now discord-video-bot
```

That restarts the bot if it crashes or the machine reboots.

---

## Settings (`.env`)

You only **must** set `DISCORD_TOKEN`. Everything else has defaults.

### Common settings

| Setting | Default | Meaning |
|---------|---------|---------|
| `DISCORD_TOKEN` | — | Bot token (required) |
| `MAX_FILE_SIZE_MB` | `25` | Max video size Discord will accept (raise if your server is boosted) |
| `MAX_DOWNLOADS_PER_USER_PER_HOUR` | `10` | Stops one person spamming downloads |
| `INCLUDE_AUTHOR` | `true` | Tags the person who shared the link |
| `INCLUDE_TITLE` | `true` | Shows the video title |
| `INCLUDE_SOURCE_URL` | `false` | Also show the original link under the video |
| `DELETE_ORIGINAL_MESSAGE` | `true` | Removes the message that only had the link |
| `COMPRESS_VIDEOS` | `true` | Shrink big files so they fit Discord |
| `ALLOWED_CHANNEL_IDS` | empty | If set, bot only works in these channels |
| `IGNORED_CHANNEL_IDS` | empty | Bot ignores these channels |

### More options

Full list lives in [`.env.example`](.env.example):

- `ALLOW_GENERIC_URLS` — try other websites, not only the big social apps  
- `CONCURRENT_DOWNLOAD_LIMIT` — how many downloads at once  
- `DOWNLOAD_TIMEOUT_SECONDS` — give up if a download takes too long  
- `TEMP_DIR` / `LOG_FILE` — where temp files and logs go  

**Tip:** To get a channel ID in Discord: User Settings → Advanced → enable Developer Mode → right‑click channel → Copy Channel ID.

---

## Example in chat

Someone posts a link. After the bot runs you see something like:

```
@alex
Cute dog compilation
```
plus the playable video file.

---

## Commands

| Command | Who can use it | What it does |
|---------|----------------|--------------|
| `!videostatus` | People with **Manage Server** | Shows size limit, rate limit, etc. |

---

## When something stops working

Social apps change their sites often. If downloads fail for a site that used to work:

```bash
source .venv/bin/activate
pip install -U yt-dlp
# restart the bot (Ctrl+C, then python main.py)
```

With Docker:

```bash
docker compose up -d --build
```

Also double-check:

1. **Message Content Intent** is still on in the Developer Portal  
2. The bot role can **Send Messages**, **Attach Files**, and **Manage Messages** in that channel  
3. Your token in `.env` has no extra spaces or quotes  

Temporary files are stored under `TEMP_DIR` (default `/tmp/discord-video-bot`) and are **deleted after each job**. The video that stays is only the one Discord uploaded.

---

## Project files (for the curious)

```
main.py                     starts the bot
config.py                   reads .env
cogs/video_downloader.py    reacts to messages
utils/download_handler.py   download + compress
utils/validators.py         finds links in text
utils/file_manager.py       temp folders
deploy/                     systemd example
Dockerfile / docker-compose.yml
```

---

## Contributing & license

- How to contribute: [CONTRIBUTING.md](CONTRIBUTING.md)  
- Security reports: [SECURITY.md](SECURITY.md)  
- License: [MIT](LICENSE) — The Khan Labs  

Run this only on servers you’re allowed to manage. You’re responsible for how you use it.
