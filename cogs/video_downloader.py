"""Message listener that rehosts social video links as Discord attachments."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque

import nextcord
from nextcord.ext import commands

from config import Settings
from utils.download_handler import DownloadError, VideoDownloader
from utils.file_manager import FileManager
from utils.validators import MatchedURL, extract_video_urls

logger = logging.getLogger(__name__)

_STATUS_WORKING = "One moment…"
_STATUS_OPTIMIZING = "Almost ready…"
_STATUS_UPLOADING = "Sending…"

_ERROR_TTL_SECONDS = 12.0
_NOTICE_TTL_SECONDS = 8.0


class RateLimiter:
    """Sliding-window per-user download rate limiter."""

    def __init__(self, max_per_hour: int) -> None:
        self.max_per_hour = max_per_hour
        self._hits: dict[int, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    def _prune(self, user_id: int, now: float) -> Deque[float]:
        window_start = now - 3600.0
        q = self._hits[user_id]
        while q and q[0] < window_start:
            q.popleft()
        return q

    async def allow(self, user_id: int) -> bool:
        """Reserve one slot. Call refund() if the job fails before upload."""
        if self.max_per_hour <= 0:
            return True

        async with self._lock:
            now = time.monotonic()
            q = self._prune(user_id, now)
            if len(q) >= self.max_per_hour:
                return False
            q.append(now)
            return True

    async def refund(self, user_id: int) -> None:
        """Undo the most recent reservation (failed download/upload)."""
        if self.max_per_hour <= 0:
            return
        async with self._lock:
            q = self._hits.get(user_id)
            if q:
                q.pop()

    async def remaining(self, user_id: int) -> int:
        async with self._lock:
            now = time.monotonic()
            q = self._prune(user_id, now)
            return max(0, self.max_per_hour - len(q))


class StatusBoard:
    """One ephemeral status message + channel typing. Always cleaned up."""

    def __init__(self, channel: nextcord.abc.Messageable) -> None:
        self.channel = channel
        self.message: nextcord.Message | None = None
        self._typing_task: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self, text: str = _STATUS_WORKING) -> None:
        if self._closed:
            return
        try:
            self.message = await self.channel.send(text)
        except nextcord.HTTPException as exc:
            logger.debug("Status message skipped: %s", exc)
            self.message = None
        self._typing_task = asyncio.create_task(self._keep_typing())

    async def set(self, text: str) -> None:
        if self._closed or self.message is None:
            return
        try:
            await self.message.edit(content=text)
        except (nextcord.HTTPException, nextcord.NotFound):
            pass

    async def close(self) -> None:
        self._closed = True
        if self._typing_task is not None:
            self._typing_task.cancel()
            try:
                await self._typing_task
            except asyncio.CancelledError:
                pass
            self._typing_task = None
        if self.message is not None:
            try:
                await self.message.delete()
            except (nextcord.HTTPException, nextcord.NotFound):
                pass
            self.message = None

    async def _keep_typing(self) -> None:
        try:
            while not self._closed:
                try:
                    async with self.channel.typing():
                        await asyncio.sleep(8)
                except (nextcord.HTTPException, asyncio.CancelledError):
                    break
                except Exception:  # noqa: BLE001
                    break
        except asyncio.CancelledError:
            return


class VideoDownloaderCog(commands.Cog):
    """Watches messages for video links and re-uploads them natively."""

    def __init__(self, bot: commands.Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings
        self.file_manager = FileManager(
            base_dir=settings.temp_dir,
            max_file_size_bytes=settings.upload_max_bytes,
        )
        # Never leave videos from a previous crash sitting on disk.
        self.file_manager.purge_all_jobs()
        self.downloader = VideoDownloader(
            file_manager=self.file_manager,
            timeout_seconds=settings.download_timeout_seconds,
            compress_videos=settings.compress_videos,
            max_file_size_bytes=settings.upload_max_bytes,
        )
        self.rate_limiter = RateLimiter(settings.max_downloads_per_user_per_hour)
        self._download_semaphore = asyncio.Semaphore(settings.concurrent_download_limit)
        self._in_flight: set[int] = set()
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _track_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _channel_allowed(self, channel_id: int) -> bool:
        if channel_id in self.settings.ignored_channel_ids:
            return False
        if self.settings.allowed_channel_ids:
            return channel_id in self.settings.allowed_channel_ids
        return True

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message) -> None:
        if message.author.bot:
            return
        if message.author == self.bot.user:
            return
        if message.guild is not None and not self._channel_allowed(message.channel.id):
            return
        if not message.content:
            return
        if message.id in self._in_flight:
            return

        matches = extract_video_urls(message.content)
        if not matches:
            return

        self._in_flight.add(message.id)
        try:
            await self._handle_video_message(message, matches)
        finally:
            self._in_flight.discard(message.id)

    async def _handle_video_message(
        self,
        message: nextcord.Message,
        matches: list[MatchedURL],
    ) -> None:
        matched = matches[0]
        user = message.author
        channel = message.channel
        in_dm = message.guild is None
        reserved = False

        logger.info(
            "Video link from %s (%s) in %s: %s [%s]",
            user,
            user.id,
            "DM" if in_dm else f"#{getattr(channel, 'name', channel.id)}",
            matched.url,
            matched.platform.value,
        )

        if not await self.rate_limiter.allow(user.id):
            await self._temp_notice(
                channel,
                f"Easy, {user.mention} — slow down a bit and try again in a while.",
                ttl=_NOTICE_TTL_SECONDS,
            )
            return
        reserved = True

        if self.settings.delete_original_message and not in_dm:
            await self._delete_message_now(message)

        status = StatusBoard(channel)
        await status.start(_STATUS_WORKING)
        success = False
        upload_size: int | None = None

        try:
            async with self._download_semaphore:
                # job_workspace always deletes the whole temp folder on exit.
                async with self.file_manager.job_workspace() as job_dir:
                    result = await self.downloader.download(matched.url, job_dir)
                    upload_size = result.path.stat().st_size

                    if result.compressed:
                        await status.set(_STATUS_OPTIMIZING)

                    await status.set(_STATUS_UPLOADING)
                    await self._upload_with_retry(
                        channel=channel,
                        author=user,
                        matched=matched,
                        file_path=result.path,
                        job_dir=job_dir,
                        status=status,
                    )
                    # Drop the file the moment Discord has it — do not keep copies.
                    await self.file_manager.delete_file(result.path)
                    success = True
        except DownloadError as exc:
            logger.error(
                "Download failed for %s (user=%s, code=%s): %s",
                matched.url,
                user.id,
                exc.code.value,
                exc,
            )
            await self._temp_notice(
                channel,
                f"{user.mention} {exc.user_message}",
                ttl=_ERROR_TTL_SECONDS,
            )
        except nextcord.HTTPException as exc:
            size_txt = (
                self.file_manager.format_size(upload_size) if upload_size is not None else "?"
            )
            logger.error(
                "Discord upload failure for %s (user=%s, size=%s): %s",
                matched.url,
                user.id,
                size_txt,
                exc,
            )
            await self._temp_notice(
                channel,
                f"{user.mention} {self._friendly_http_error(exc)}",
                ttl=_ERROR_TTL_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception(
                "Unexpected error processing %s for user %s",
                matched.url,
                user.id,
            )
            await self._temp_notice(
                channel,
                f"{user.mention} Something went wrong — try another link.",
                ttl=_ERROR_TTL_SECONDS,
            )
        finally:
            if reserved and not success:
                await self.rate_limiter.refund(user.id)
            try:
                await status.close()
            except Exception:  # noqa: BLE001
                pass

    async def _delete_message_now(self, message: nextcord.Message) -> None:
        try:
            await message.delete()
        except nextcord.Forbidden:
            logger.warning(
                "Missing permission to delete message %s in channel %s",
                message.id,
                message.channel.id,
            )
        except nextcord.NotFound:
            pass
        except nextcord.HTTPException as exc:
            logger.warning("Failed to delete original message %s: %s", message.id, exc)

    async def _upload_with_retry(
        self,
        *,
        channel: nextcord.abc.Messageable,
        author: nextcord.abc.User,
        matched: MatchedURL,
        file_path: Path,
        job_dir: Path,
        status: StatusBoard,
    ) -> None:
        path = file_path
        last_http: nextcord.HTTPException | None = None

        for attempt in range(1, 3):
            size = path.stat().st_size
            logger.info(
                "Upload attempt %d for %s (%s)",
                attempt,
                author.id,
                self.file_manager.format_size(size),
            )
            try:
                await self._send_video_file(channel, path)
                logger.info(
                    "Uploaded rehosted video for %s from %s",
                    author.id,
                    matched.url,
                )
                return
            except nextcord.HTTPException as exc:
                last_http = exc
                too_large = exc.status == 413 or getattr(exc, "code", None) == 40005
                if not too_large or attempt >= 2:
                    raise
                logger.warning(
                    "Discord rejected upload (%s, %s); compressing harder and retrying",
                    exc,
                    self.file_manager.format_size(size),
                )
                await status.set(_STATUS_OPTIMIZING)
                target_budget = min(
                    int(size * 0.6),
                    int(self.settings.upload_max_bytes * 0.75),
                )
                smaller = await self.downloader.force_compress(
                    path,
                    job_dir,
                    target_bytes=max(target_budget, 4 * 1024 * 1024),
                )
                if smaller is None or smaller.stat().st_size >= size:
                    raise
                path = smaller
                await status.set(_STATUS_UPLOADING)

        if last_http is not None:
            raise last_http

    async def _send_video_file(
        self,
        channel: nextcord.abc.Messageable,
        file_path: Path,
    ) -> None:
        upload_name = "video.mp4"
        if file_path.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"}:
            upload_name = f"video{file_path.suffix.lower()}"

        # Read into memory-safe stream; close handle before caller deletes the file.
        with file_path.open("rb") as fp:
            discord_file = nextcord.File(fp, filename=upload_name)
            await channel.send(file=discord_file)
        # File handle is closed here; bytes already uploaded to Discord.

    @staticmethod
    def _friendly_http_error(exc: nextcord.HTTPException) -> str:
        if exc.status == 413 or getattr(exc, "code", None) == 40005:
            return "That video is too large for Discord."
        if exc.status == 403:
            return "I don’t have permission to upload here."
        if exc.status == 429:
            return "Discord rate-limited me — try again shortly."
        return "Couldn’t send that video. Try again in a second."

    async def _temp_notice(
        self,
        channel: nextcord.abc.Messageable,
        content: str,
        *,
        ttl: float,
    ) -> None:
        try:
            msg = await channel.send(content)
        except nextcord.HTTPException as exc:
            logger.warning("Failed to send notice: %s", exc)
            return

        async def _vanish() -> None:
            try:
                await asyncio.sleep(ttl)
                await msg.delete()
            except (nextcord.HTTPException, nextcord.NotFound, asyncio.CancelledError):
                pass

        self._track_task(asyncio.create_task(_vanish()))

    @commands.command(name="videostatus")
    @commands.has_permissions(manage_guild=True)
    async def video_status(self, ctx: commands.Context) -> None:
        """Show downloader config (manage server required)."""
        if ctx.guild is None:
            await ctx.send("This command only works in a server.")
            return
        remaining = await self.rate_limiter.remaining(ctx.author.id)
        embed = nextcord.Embed(
            title="Video bot",
            color=0x5865F2,
            description="Quiet rehosting for social clips.",
        )
        embed.add_field(name="Max size", value=f"{self.settings.max_file_size_mb} MB", inline=True)
        embed.add_field(
            name="Upload budget",
            value=f"{self.settings.upload_max_bytes / (1024 * 1024):.1f} MB",
            inline=True,
        )
        embed.add_field(
            name="Your remaining",
            value=f"{remaining}/{self.settings.max_downloads_per_user_per_hour}",
            inline=True,
        )
        embed.add_field(
            name="Queue slots",
            value=str(self.settings.concurrent_download_limit),
            inline=True,
        )
        await ctx.send(embed=embed)


def setup(bot: commands.Bot) -> None:
    settings = getattr(bot, "settings", None)
    if settings is None:
        raise RuntimeError("Bot is missing settings; load VideoDownloaderCog from main.py")
    bot.add_cog(VideoDownloaderCog(bot, settings))
