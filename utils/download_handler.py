"""yt-dlp based video downloader with compression and typed errors."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yt_dlp

from utils.file_manager import FileManager

logger = logging.getLogger(__name__)


class DownloadErrorCode(str, Enum):
    PRIVATE = "private"
    DELETED = "deleted"
    GEO_BLOCKED = "geo_blocked"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    TOO_LARGE = "too_large"
    COMPRESSION_FAILED = "compression_failed"
    NETWORK = "network"
    UNKNOWN = "unknown"


class DownloadError(Exception):
    """Raised when a video cannot be downloaded or prepared for upload."""

    def __init__(self, message: str, code: DownloadErrorCode = DownloadErrorCode.UNKNOWN) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = _user_message_for(code, message)


def _user_message_for(code: DownloadErrorCode, technical: str) -> str:
    # Short, human lines — no platform names, no tech jargon in chat.
    mapping = {
        DownloadErrorCode.PRIVATE: "That video is private.",
        DownloadErrorCode.DELETED: "That video isn’t available anymore.",
        DownloadErrorCode.GEO_BLOCKED: "That video isn’t available here.",
        DownloadErrorCode.UNSUPPORTED: "Can’t pull video from that link.",
        DownloadErrorCode.TIMEOUT: "That took too long — try again.",
        DownloadErrorCode.TOO_LARGE: "That clip is too long/large for Discord.",
        DownloadErrorCode.COMPRESSION_FAILED: "Couldn’t shrink that video enough for Discord.",
        DownloadErrorCode.NETWORK: "Network hiccup — try that link again.",
        DownloadErrorCode.UNKNOWN: "Couldn’t grab that video.",
    }
    return mapping.get(code, "Couldn’t grab that video.")


@dataclass(slots=True)
class DownloadResult:
    path: Path
    title: str | None
    original_url: str
    filesize: int
    compressed: bool = False


# Compression attempts: progressively smaller resolution + lower audio bitrate.
# Bitrate is calculated per attempt from remaining size budget and duration.
_COMPRESS_LADDER: list[dict[str, Any]] = [
    {"max_width": 1280, "audio_kbps": 96, "preset": "veryfast", "size_ratio": 0.92},
    {"max_width": 854, "audio_kbps": 64, "preset": "veryfast", "size_ratio": 0.88},
    {"max_width": 640, "audio_kbps": 48, "preset": "faster", "size_ratio": 0.85},
    {"max_width": 480, "audio_kbps": 32, "preset": "faster", "size_ratio": 0.80},
]


class VideoDownloader:
    """Wraps yt-dlp downloads in an asyncio-friendly interface."""

    def __init__(
        self,
        file_manager: FileManager,
        timeout_seconds: float = 120.0,
        compress_videos: bool = True,
        max_file_size_bytes: int | None = None,
    ) -> None:
        self.file_manager = file_manager
        self.timeout_seconds = timeout_seconds
        self.compress_videos = compress_videos
        self.max_file_size_bytes = max_file_size_bytes or file_manager.max_file_size_bytes

    async def download(self, url: str, job_dir: Path) -> DownloadResult:
        """
        Download a video into job_dir.

        Runs yt-dlp in a worker thread so the event loop stays responsive.
        Oversized files are compressed to fit under max_file_size_bytes when possible.
        """
        logger.info("Starting download for %s into %s", url, job_dir)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._download_sync, url, job_dir),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.error("Download timed out for %s after %.1fs", url, self.timeout_seconds)
            raise DownloadError(
                f"Download timed out after {self.timeout_seconds:.0f}s",
                DownloadErrorCode.TIMEOUT,
            ) from exc

        path = result.path
        compressed = False

        if self.file_manager.exceeds_limit(path):
            size = self.file_manager.format_size(path.stat().st_size)
            limit = self.file_manager.format_size(self.max_file_size_bytes)
            logger.info(
                "File %s is %s (limit %s); will compress to fit Discord",
                path.name,
                size,
                limit,
            )

            if not self.compress_videos:
                raise DownloadError(
                    f"Video is {size} which exceeds the {limit} Discord upload limit",
                    DownloadErrorCode.TOO_LARGE,
                )

            fitted = await self._compress_to_limit(path, job_dir)
            if fitted is None:
                raise DownloadError(
                    f"Video is {size} (limit {limit}) and could not be compressed under the limit",
                    DownloadErrorCode.COMPRESSION_FAILED
                    if not ffmpeg_available()
                    else DownloadErrorCode.TOO_LARGE,
                )
            path = fitted
            compressed = True

        if self.file_manager.exceeds_limit(path):
            size = self.file_manager.format_size(path.stat().st_size)
            limit = self.file_manager.format_size(self.max_file_size_bytes)
            raise DownloadError(
                f"Video is {size} which exceeds the {limit} Discord upload limit",
                DownloadErrorCode.TOO_LARGE,
            )

        final = DownloadResult(
            path=path,
            title=result.title,
            original_url=result.original_url,
            filesize=path.stat().st_size,
            compressed=compressed,
        )
        logger.info(
            "Download ready: %s (%s, compressed=%s)",
            path.name,
            self.file_manager.format_size(final.filesize),
            final.compressed,
        )
        return final

    def _download_sync(self, url: str, job_dir: Path) -> DownloadResult:
        # X/Twitter: prefer public fixup APIs (handles many sensitive posts),
        # then fall back to yt-dlp once — no redundant second API pass.
        if self._is_twitter_url(url):
            try:
                return self._download_twitter_fallback(url, job_dir)
            except DownloadError as exc:
                logger.info(
                    "Twitter API fallback failed (%s); trying yt-dlp for %s",
                    exc.code.value,
                    url,
                )
                return self._download_with_ytdlp(url, job_dir)

        return self._download_with_ytdlp(url, job_dir)

    def _download_with_ytdlp(self, url: str, job_dir: Path) -> DownloadResult:
        output_template = str(job_dir / "%(title).80B [%(id)s].%(ext)s")
        # Prefer reasonable quality; we compress later if still over Discord's limit.
        ydl_opts: dict[str, Any] = {
            "outtmpl": output_template,
            "format": (
                "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4][height<=1080]"
                "/bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/best"
            ),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "retries": 2,
            "fragment_retries": 2,
            "socket_timeout": min(30, int(self.timeout_seconds)),
            "writethumbnail": False,
            "writesubtitles": False,
            "writeinfojson": False,
        }

        title: str | None = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError("No metadata returned", DownloadErrorCode.UNKNOWN)
                if "entries" in info and info["entries"]:
                    info = next((e for e in info["entries"] if e), info)
                title = info.get("title") if isinstance(info, dict) else None
        except DownloadError:
            raise
        except yt_dlp.utils.DownloadError as exc:
            raise self._classify_ytdlp_error(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected download failure for %s", url)
            raise DownloadError(str(exc), DownloadErrorCode.UNKNOWN) from exc

        path = self.file_manager.find_downloaded_file(job_dir)
        if path is None:
            raise DownloadError(
                "Download completed but no media file was found",
                DownloadErrorCode.UNKNOWN,
            )

        return DownloadResult(
            path=path,
            title=title,
            original_url=url,
            filesize=path.stat().st_size,
            compressed=False,
        )

    @staticmethod
    def _is_twitter_url(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(h in host for h in ("twitter.com", "x.com", "vxtwitter.com", "fxtwitter.com"))

    @staticmethod
    def _twitter_status_id(url: str) -> str | None:
        match = re.search(r"/status(?:es)?/(\d+)", url)
        return match.group(1) if match else None

    def _download_twitter_fallback(self, url: str, job_dir: Path) -> DownloadResult:
        """
        Fetch X videos via public fixup APIs (works for many sensitive posts yt-dlp skips).
        """
        status_id = self._twitter_status_id(url)
        if not status_id:
            raise DownloadError("Not a status URL", DownloadErrorCode.UNSUPPORTED)

        # Parse username when present for vxtwitter path form.
        user_match = re.search(
            r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)/status",
            url,
            re.IGNORECASE,
        )
        username = user_match.group(1) if user_match else "i"

        endpoints = [
            f"https://api.fxtwitter.com/status/{status_id}",
            f"https://api.vxtwitter.com/{username}/status/{status_id}",
        ]

        last_error: str | None = None
        for api_url in endpoints:
            try:
                payload = self._http_json(api_url)
            except DownloadError as exc:
                last_error = str(exc)
                continue

            candidates, title = self._extract_twitter_media_candidates(payload)
            if not candidates:
                last_error = "No video media in API response"
                continue

            # Prefer highest quality that is estimated to fit Discord's limit.
            ordered = self._rank_twitter_candidates(candidates)
            for rank, (bitrate, media_url, duration) in enumerate(ordered, start=1):
                target = job_dir / f"x-{status_id}-{rank}.mp4"
                est = self._estimate_bytes(bitrate, duration)
                logger.info(
                    "X fallback try %d/%d bitrate=%s est=%s → %s",
                    rank,
                    len(ordered),
                    bitrate or "?",
                    self.file_manager.format_size(est) if est else "?",
                    media_url[:90],
                )
                try:
                    self._http_download(media_url, target)
                except DownloadError as exc:
                    last_error = str(exc)
                    continue
                if not target.exists() or target.stat().st_size == 0:
                    last_error = "Empty media download"
                    continue

                size = target.stat().st_size
                # If still over limit, try a lower quality variant before ffmpeg.
                if size > self.max_file_size_bytes and rank < len(ordered):
                    logger.info(
                        "X variant %s over limit (%s); trying smaller quality",
                        rank,
                        self.file_manager.format_size(size),
                    )
                    try:
                        target.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue

                return DownloadResult(
                    path=target,
                    title=title,
                    original_url=url,
                    filesize=size,
                    compressed=False,
                )

        raise DownloadError(
            last_error or "Twitter fallback failed",
            DownloadErrorCode.UNKNOWN,
        )

    def _rank_twitter_candidates(
        self,
        candidates: list[tuple[int, str, float | None]],
    ) -> list[tuple[int, str, float | None]]:
        """
        Order formats: best quality that likely fits under max size first,
        then smaller ones, then oversized high-quality as last resort (ffmpeg).
        """
        # Prefer variants well under the hard Discord ceiling.
        budget = int(self.max_file_size_bytes * 0.85)
        fitting: list[tuple[int, str, float | None]] = []
        oversized: list[tuple[int, str, float | None]] = []

        # Dedupe by URL.
        seen: set[str] = set()
        unique: list[tuple[int, str, float | None]] = []
        for item in candidates:
            if item[1] in seen:
                continue
            seen.add(item[1])
            unique.append(item)

        for bitrate, media_url, duration in unique:
            est = self._estimate_bytes(bitrate, duration)
            if est is not None and est <= budget:
                fitting.append((bitrate, media_url, duration))
            else:
                oversized.append((bitrate, media_url, duration))

        # Among fitting: highest bitrate first. Among oversized: lowest first (easier compress).
        fitting.sort(key=lambda x: x[0], reverse=True)
        oversized.sort(key=lambda x: x[0] if x[0] else 10**9)
        return fitting + oversized

    @staticmethod
    def _estimate_bytes(bitrate: int, duration: float | None) -> int | None:
        if bitrate <= 0 or not duration or duration <= 0:
            return None
        # bitrate is often bits/sec; add small container overhead.
        return int(bitrate * duration / 8 * 1.05)

    def _extract_twitter_media_candidates(
        self,
        payload: dict[str, Any],
    ) -> tuple[list[tuple[int, str, float | None]], str | None]:
        """
        Return ([(bitrate, url, duration_seconds), ...], title) from fixup APIs.
        """
        title: str | None = None
        candidates: list[tuple[int, str, float | None]] = []

        tweet = payload.get("tweet") if isinstance(payload.get("tweet"), dict) else payload
        if not isinstance(tweet, dict):
            return [], None

        text = tweet.get("text") or tweet.get("raw_text")
        if isinstance(text, dict):
            title = text.get("text")
        elif isinstance(text, str):
            title = text

        def _add(url: str | None, bitrate: int = 0, duration: float | None = None) -> None:
            if not url or ".m3u8" in url:
                return
            candidates.append((int(bitrate or 0), url, duration))

        media = tweet.get("media") if isinstance(tweet.get("media"), dict) else {}
        for key in ("videos", "all", "video"):
            items = media.get(key)
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("type") and item.get("type") not in {"video", "gif", "animated_gif"}:
                    continue
                duration = item.get("duration")
                try:
                    duration_f = float(duration) if duration is not None else None
                except (TypeError, ValueError):
                    duration_f = None
                # ms sometimes.
                if duration_f is not None and duration_f > 1000:
                    duration_f = duration_f / 1000.0

                formats = item.get("formats") or item.get("variants") or []
                if isinstance(formats, list) and formats:
                    for fmt in formats:
                        if not isinstance(fmt, dict):
                            continue
                        _add(fmt.get("url"), int(fmt.get("bitrate") or 0), duration_f)
                _add(item.get("url"), int(item.get("bitrate") or 0), duration_f)

        # vxtwitter
        for url in tweet.get("mediaURLs") or []:
            if isinstance(url, str):
                _add(url, 0, None)
        for item in tweet.get("media_extended") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"video", "gif", "animated_gif", None}:
                dur_ms = item.get("duration_millis")
                duration_f = (float(dur_ms) / 1000.0) if dur_ms else None
                _add(item.get("url"), 0, duration_f)

        return candidates, title

    def _http_json(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DiscordVideoBot/1.0)",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=min(30, int(self.timeout_seconds))) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise DownloadError(f"HTTP {exc.code} from {url}", DownloadErrorCode.NETWORK) from exc
        except urllib.error.URLError as exc:
            raise DownloadError(f"Network error: {exc}", DownloadErrorCode.NETWORK) from exc

        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise DownloadError("Invalid JSON from media API", DownloadErrorCode.UNKNOWN) from exc
        if not isinstance(data, dict):
            raise DownloadError("Unexpected media API payload", DownloadErrorCode.UNKNOWN)
        return data

    def _http_download(self, url: str, target: Path) -> None:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DiscordVideoBot/1.0)",
                "Accept": "*/*",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=int(self.timeout_seconds)) as resp:
                with target.open("wb") as out:
                    shutil.copyfileobj(resp, out)
        except urllib.error.HTTPError as exc:
            raise DownloadError(f"Media HTTP {exc.code}", DownloadErrorCode.NETWORK) from exc
        except urllib.error.URLError as exc:
            raise DownloadError(f"Media network error: {exc}", DownloadErrorCode.NETWORK) from exc

    def _classify_ytdlp_error(self, message: str) -> DownloadError:
        lower = message.lower()
        logger.warning("yt-dlp error: %s", message)

        if any(k in lower for k in ("private", "login required", "sign in", "only available")):
            return DownloadError(message, DownloadErrorCode.PRIVATE)
        if any(
            k in lower
            for k in (
                "has been removed",
                "does not exist",
                "not available",
                "deleted",
                "404",
                "video unavailable",
            )
        ):
            return DownloadError(message, DownloadErrorCode.DELETED)
        if any(k in lower for k in ("geo", "not available in your country", "region", "blocked")):
            return DownloadError(message, DownloadErrorCode.GEO_BLOCKED)
        if any(
            k in lower
            for k in (
                "unsupported url",
                "no suitable extractor",
                "is not a valid url",
            )
        ):
            return DownloadError(message, DownloadErrorCode.UNSUPPORTED)
        if any(k in lower for k in ("timed out", "timeout", "network", "connection", "ssl")):
            return DownloadError(message, DownloadErrorCode.NETWORK)
        return DownloadError(message, DownloadErrorCode.UNKNOWN)

    async def force_compress(
        self,
        source: Path,
        job_dir: Path,
        *,
        target_bytes: int | None = None,
    ) -> Path | None:
        """Public helper: re-encode under target_bytes (defaults to max upload budget)."""
        return await self._compress_to_limit(
            source,
            job_dir,
            hard_limit_bytes=target_bytes or self.max_file_size_bytes,
        )

    async def _compress_to_limit(
        self,
        source: Path,
        job_dir: Path,
        *,
        hard_limit_bytes: int | None = None,
    ) -> Path | None:
        """
        Re-encode the video so the output is under hard_limit_bytes.

        Uses duration-aware target bitrates and a resolution ladder. Returns the
        path to a file that fits, or None if compression is impossible.
        """
        limit = hard_limit_bytes or self.max_file_size_bytes
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg:
            logger.warning("ffmpeg not found; cannot compress oversized video")
            return None

        duration = await self._probe_duration(source, ffprobe)
        if duration is None or duration <= 0:
            # Fall back to a generous default so bitrate math still works.
            duration = 60.0
            logger.warning("Could not probe duration for %s; assuming %.0fs", source.name, duration)

        current = source
        # Allow longer wall time for multi-pass re-encodes of big clips.
        encode_timeout = max(self.timeout_seconds, 180.0) + min(duration * 2.0, 300.0)

        for attempt, step in enumerate(_COMPRESS_LADDER, start=1):
            target_bytes = int(limit * step["size_ratio"])
            audio_kbps = int(step["audio_kbps"])
            video_kbps = self._target_video_bitrate_kbps(
                target_bytes=target_bytes,
                duration_seconds=duration,
                audio_kbps=audio_kbps,
            )
            if video_kbps < 50:
                # Bitrate floor: below this quality is useless / encode may fail.
                logger.warning(
                    "Target video bitrate too low (%d kbps) for attempt %d; skipping",
                    video_kbps,
                    attempt,
                )
                continue

            out = job_dir / f"{source.stem}.fit{attempt}.mp4"
            logger.info(
                "Compress attempt %d/%d: max_w=%s v=%dk a=%dk target~%s (src=%s)",
                attempt,
                len(_COMPRESS_LADDER),
                step["max_width"],
                video_kbps,
                audio_kbps,
                self.file_manager.format_size(target_bytes),
                self.file_manager.format_size(current.stat().st_size),
            )

            ok = await self._run_ffmpeg_fit(
                ffmpeg=ffmpeg,
                source=current,
                target=out,
                max_width=int(step["max_width"]),
                video_kbps=video_kbps,
                audio_kbps=audio_kbps,
                preset=str(step["preset"]),
                timeout=encode_timeout,
            )
            if not ok or not out.exists() or out.stat().st_size == 0:
                continue

            out_size = out.stat().st_size
            logger.info(
                "Compress attempt %d produced %s (limit %s)",
                attempt,
                self.file_manager.format_size(out_size),
                self.file_manager.format_size(limit),
            )

            if out_size <= limit:
                await self._safe_unlink(source)
                if current != source:
                    await self._safe_unlink(current)
                # Stable name for Discord attachment.
                final = job_dir / f"{source.stem}.discord.mp4"
                out.replace(final)
                return final

            # Use this smaller intermediate as next source if it improved.
            if out_size < current.stat().st_size:
                if current != source:
                    await self._safe_unlink(current)
                current = out
            else:
                await self._safe_unlink(out)

        logger.error(
            "All compression attempts failed to get under %s (last size %s)",
            self.file_manager.format_size(limit),
            self.file_manager.format_size(current.stat().st_size),
        )
        return None

    @staticmethod
    def _target_video_bitrate_kbps(
        target_bytes: int,
        duration_seconds: float,
        audio_kbps: int,
    ) -> int:
        """Compute video bitrate (kbps) to aim for a total file size."""
        # bits available for A/V, leave ~3% mux overhead
        total_bits = target_bytes * 8 * 0.97
        total_kbps = total_bits / duration_seconds / 1000.0
        video_kbps = total_kbps - audio_kbps
        return max(1, int(math.floor(video_kbps)))

    async def _probe_duration(self, path: Path, ffprobe: str | None) -> float | None:
        if not ffprobe:
            return None
        cmd = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except (asyncio.TimeoutError, OSError) as exc:
            logger.warning("ffprobe failed for %s: %s", path, exc)
            return None

        if proc.returncode != 0:
            return None
        try:
            data = json.loads(stdout.decode("utf-8", errors="replace"))
            duration = float(data["format"]["duration"])
            return duration if duration > 0 else None
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def _run_ffmpeg_fit(
        self,
        *,
        ffmpeg: str,
        source: Path,
        target: Path,
        max_width: int,
        video_kbps: int,
        audio_kbps: int,
        preset: str,
        timeout: float,
    ) -> bool:
        """
        Single-pass H.264 encode with maxrate/bufsize so size tracks the budget.

        scale keeps aspect ratio; even width/height required by yuv420p.
        """
        # Scale down if wider than max_width; never upscale.
        vf = (
            f"scale='min({max_width},iw)':'-2',"
            "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        )
        # bufsize ~2s of video helps hit the size target without huge spikes.
        bufsize = f"{max(video_kbps * 2, 200)}k"
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-b:v",
            f"{video_kbps}k",
            "-maxrate",
            f"{video_kbps}k",
            "-bufsize",
            bufsize,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            f"{audio_kbps}k",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(target),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("ffmpeg timed out after %.0fs for %s", timeout, source.name)
            return False
        except OSError as exc:
            logger.error("ffmpeg failed to start: %s", exc)
            return False

        if proc.returncode != 0:
            err_text = (stderr or b"").decode("utf-8", errors="replace")[-800:]
            logger.error("ffmpeg exited %s: %s", proc.returncode, err_text)
            return False
        return True

    @staticmethod
    async def _safe_unlink(path: Path) -> None:
        try:
            await asyncio.to_thread(path.unlink, True)
        except OSError:
            pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None
