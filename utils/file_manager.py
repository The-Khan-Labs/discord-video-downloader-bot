"""Temporary file lifecycle helpers for downloaded videos.

Videos are never kept after processing: each job lives in an isolated
directory that is always deleted when the job finishes (success or failure).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

logger = logging.getLogger(__name__)


class FileManager:
    """Creates isolated temp workspaces and enforces Discord size limits."""

    def __init__(self, base_dir: Path, max_file_size_bytes: int) -> None:
        self.base_dir = base_dir
        self.max_file_size_bytes = max_file_size_bytes
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_job_dir(self) -> Path:
        """Create a unique subdirectory for a single download job."""
        job_dir = self.base_dir / f"job-{uuid.uuid4().hex}"
        job_dir.mkdir(parents=True, exist_ok=False)
        logger.debug("Created job directory %s", job_dir)
        return job_dir

    async def cleanup(self, path: Path | None) -> None:
        """Remove a file or directory tree without raising."""
        if path is None:
            return
        await asyncio.to_thread(self._cleanup_sync, path)

    async def delete_file(self, path: Path | None) -> None:
        """Delete a single file immediately (e.g. right after Discord upload)."""
        if path is None:
            return
        await asyncio.to_thread(self._delete_file_sync, path)

    @staticmethod
    def _delete_file_sync(path: Path) -> None:
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
                logger.info("Deleted temp video %s", path.name)
            elif path.exists():
                # Unexpected non-file: remove aggressively.
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to delete temp file %s: %s", path, exc)

    @staticmethod
    def _cleanup_sync(path: Path) -> None:
        try:
            if path.is_dir():
                # Wipe every file inside before rmtree for clearer logging.
                for child in path.rglob("*"):
                    if child.is_file():
                        try:
                            child.unlink(missing_ok=True)
                        except OSError:
                            pass
                shutil.rmtree(path, ignore_errors=True)
                logger.info("Removed job workspace %s", path.name)
            elif path.exists():
                path.unlink(missing_ok=True)
                logger.info("Deleted temp path %s", path)
        except OSError as exc:
            logger.warning("Failed to clean up %s: %s", path, exc)

    def get_file_size(self, path: Path) -> int:
        return path.stat().st_size

    def exceeds_limit(self, path: Path) -> bool:
        return self.get_file_size(path) > self.max_file_size_bytes

    def format_size(self, size_bytes: int) -> str:
        mb = size_bytes / (1024 * 1024)
        if mb >= 1:
            return f"{mb:.1f} MB"
        kb = size_bytes / 1024
        return f"{kb:.1f} KB"

    def find_downloaded_file(self, job_dir: Path) -> Path | None:
        """
        Locate the primary media file inside a job directory.

        Prefers common video extensions and falls back to the largest non-empty file.
        """
        if not job_dir.exists():
            return None

        video_exts = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi"}
        candidates = [
            p
            for p in job_dir.rglob("*")
            if p.is_file() and not p.name.endswith(".part") and p.stat().st_size > 0
        ]
        if not candidates:
            return None

        videos = [p for p in candidates if p.suffix.lower() in video_exts]
        pool = videos or candidates
        return max(pool, key=lambda p: p.stat().st_size)

    @asynccontextmanager
    async def job_workspace(self) -> AsyncIterator[Path]:
        """
        Isolated workspace for one download/upload.

        Always deletes the entire directory on exit — success, failure, or cancel.
        """
        job_dir = self.create_job_dir()
        try:
            yield job_dir
        finally:
            await self.cleanup(job_dir)

    def ensure_base_dir(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def purge_all_jobs(self) -> int:
        """Delete every job-* directory (startup sweep). Keeps bot.lock."""
        removed = 0
        if not self.base_dir.exists():
            return 0
        for entry in list(self.base_dir.iterdir()):
            if not entry.is_dir() or not entry.name.startswith("job-"):
                continue
            try:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
            except OSError:
                continue
        if removed:
            logger.info("Purged %d leftover job directories from %s", removed, self.base_dir)
        return removed

    def purge_stale(self, max_age_seconds: int = 3600) -> int:
        """
        Best-effort cleanup of abandoned job directories older than max_age_seconds.

        Returns the number of directories removed.
        """
        removed = 0
        now = time.time()
        if not self.base_dir.exists():
            return 0

        for entry in self.base_dir.iterdir():
            if not entry.is_dir() or not entry.name.startswith("job-"):
                continue
            try:
                age = now - entry.stat().st_mtime
                if age > max_age_seconds:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
            except OSError:
                continue

        if removed:
            logger.info("Purged %d stale job directories from %s", removed, self.base_dir)
        return removed


def make_temp_filename(prefix: str = "video", suffix: str = ".mp4") -> str:
    """Return a unique filename (not a full path)."""
    return f"{prefix}-{uuid.uuid4().hex}{suffix}"


def system_temp_dir() -> Path:
    return Path(tempfile.gettempdir())
