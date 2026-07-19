# Security

## Reporting

If you find something that can leak a token, write outside the temp dir, or otherwise cause real harm:

1. Don’t file a public issue with exploit details.
2. Use GitHub Security Advisories on this repo, or contact the maintainers privately.
3. Include repro steps and impact.

## Running this bot

- Keep `DISCORD_TOKEN` in `.env` only; never paste it into issues or screenshots.
- Use `ALLOWED_CHANNEL_IDS` if the bot is in a large server.
- Update yt-dlp regularly.
- Run as an unprivileged user if you can.
- Disk: jobs are cleaned up, but watch `TEMP_DIR` if something crashes mid-download.

This project downloads third-party media and rehosts it on Discord. You’re on the hook for your own usage and legal compliance.
