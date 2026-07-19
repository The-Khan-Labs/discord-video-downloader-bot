# Security

## Reporting a vulnerability

If you find a security issue (token leaks, path traversal, remote code abuse, etc.):

1. **Do not** open a public GitHub issue.
2. Contact the repository owner privately (GitHub Security Advisories preferred).
3. Include steps to reproduce and impact.

## Hardening notes for operators

- Never commit `.env` or paste bot tokens into issues.
- Restrict the bot to trusted servers/channels (`ALLOWED_CHANNEL_IDS`).
- Keep `yt-dlp` updated: `pip install -U yt-dlp`.
- Run under a dedicated OS user with minimal filesystem permissions.
- Temp files live under `TEMP_DIR` and should be deleted after each job; still monitor disk use.
- Generic URL mode can be disabled (`ALLOW_GENERIC_URLS=false`) to only process known social hosts.

## Scope

This bot downloads public media from third-party sites and re-uploads it to Discord. Operators are responsible for complying with Discord’s Terms of Service, copyright law, and local regulations.
