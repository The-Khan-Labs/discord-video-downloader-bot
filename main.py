"""Discord social-video rehost bot entry point."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import nextcord
from nextcord.ext import commands

from cogs.video_downloader import VideoDownloaderCog
from config import Settings, load_settings
from utils.process_lock import ProcessLock


def setup_logging(settings: Settings) -> None:
    """
    Configure logging to a rotating file, and to stdout only when interactive.

    Avoids double-writing every line when the process is started with
    `>> logs/bot.log` (nohup/restart scripts).
    """
    log_path = settings.log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level, logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if root.handlers:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Only mirror to stdout when attached to a real terminal (not nohup redirect).
    if sys.stdout.isatty():
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    logging.getLogger("nextcord").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def build_bot(settings: Settings) -> commands.Bot:
    intents = nextcord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    # Required for receiving DMs (bot ↔ user).
    intents.dm_messages = True

    bot = commands.Bot(
        command_prefix=commands.when_mentioned_or("!"),
        intents=intents,
        help_command=None,
    )
    bot.settings = settings  # type: ignore[attr-defined]
    bot.add_cog(VideoDownloaderCog(bot, settings))

    @bot.event
    async def on_ready() -> None:
        user = bot.user
        logging.getLogger(__name__).info(
            "Logged in as %s (id=%s) | guilds=%d",
            user,
            getattr(user, "id", "?"),
            len(bot.guilds),
        )
        try:
            await bot.change_presence(
                activity=nextcord.Activity(
                    type=nextcord.ActivityType.watching,
                    name="for video links",
                ),
                status=nextcord.Status.online,
            )
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).debug("Could not set presence", exc_info=True)

    @bot.event
    async def on_command_error(ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.MissingPermissions):
            if ctx.guild is not None:
                await ctx.send("You need Manage Server permission for that command.")
            return
        if isinstance(error, commands.CommandNotFound):
            return
        logging.getLogger(__name__).error("Command error: %s", error, exc_info=error)

    return bot


def main() -> None:
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    lock_path = Path(settings.temp_dir) / "bot.lock"
    lock = ProcessLock(lock_path)
    try:
        lock.acquire()
    except RuntimeError as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(settings)
    logger = logging.getLogger(__name__)
    logger.info(
        "Starting video bot (max_size=%sMB, upload_budget=%.1fMB, rate=%s/hour, concurrency=%s)",
        settings.max_file_size_mb,
        settings.upload_max_bytes / (1024 * 1024),
        settings.max_downloads_per_user_per_hour,
        settings.concurrent_download_limit,
    )

    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    bot = build_bot(settings)

    try:
        bot.run(settings.discord_token)
    except nextcord.LoginFailure:
        logger.error("Invalid DISCORD_TOKEN — check your .env file.")
        lock.release()
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutting down (keyboard interrupt).")
    except Exception:
        logger.exception("Bot crashed")
        raise
    finally:
        lock.release()


if __name__ == "__main__":
    main()
