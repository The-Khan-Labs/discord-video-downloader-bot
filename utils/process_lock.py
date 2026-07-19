"""Single-instance process lock so two bot processes cannot run at once."""

from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class ProcessLock:
    """
    Exclusive lock file + PID.

    Uses fcntl.flock when available so a crashed process releases the lock
    when the FD is closed by the kernel.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Open for read/write; create if missing.
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(fd)
                other = self._read_pid()
                raise RuntimeError(
                    f"Another bot instance is already running"
                    f"{f' (pid {other})' if other else ''}. "
                    f"Stop it first or remove {self.path}"
                ) from exc
        except ImportError:
            # Non-Unix: best-effort PID file only.
            existing = self._read_pid()
            if existing and self._pid_alive(existing):
                os.close(fd)
                raise RuntimeError(
                    f"Another bot instance is already running (pid {existing})."
                )

        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        self._fd = fd
        atexit.register(self.release)
        logger.info("Acquired process lock %s (pid %s)", self.path, os.getpid())

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            import fcntl

            fcntl.flock(self._fd, fcntl.LOCK_UN)
        except Exception:  # noqa: BLE001
            pass
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None
        try:
            if self.path.exists():
                # Only remove if it still points at us.
                if self._read_pid() == os.getpid():
                    self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def _read_pid(self) -> int | None:
        try:
            text = self.path.read_text(encoding="utf-8").strip()
            return int(text.splitlines()[0]) if text else None
        except (OSError, ValueError, IndexError):
            return None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
