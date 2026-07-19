"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_csv_ints(name: str) -> list[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    values: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            values.append(int(part))
    return values


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the Discord video bot."""

    discord_token: str
    max_file_size_mb: int = 25
    max_downloads_per_user_per_hour: int = 10
    download_timeout_seconds: float = 120.0
    compress_videos: bool = True
    allowed_channel_ids: list[int] = field(default_factory=list)
    ignored_channel_ids: list[int] = field(default_factory=list)
    temp_dir: Path = field(default_factory=lambda: Path("/tmp/discord-video-bot"))
    log_file: Path = field(default_factory=lambda: Path("logs/bot.log"))
    log_level: str = "INFO"
    delete_original_message: bool = True
    include_source_url: bool = False
    concurrent_download_limit: int = 3

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def upload_max_bytes(self) -> int:
        """
        Practical Discord upload budget.

        Discord advertises 25MB, but multipart overhead / CDN checks often reject
        files close to the ceiling. Stay a few MB under the configured max.
        """
        configured = self.max_file_size_bytes
        # Keep at least ~2MB of headroom under the configured cap (min 8MB floor).
        headroom = max(2 * 1024 * 1024, configured // 10)
        return max(8 * 1024 * 1024, configured - headroom)


def load_settings() -> Settings:
    """Load and validate settings from the environment."""
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "DISCORD_TOKEN is required. Copy .env.example to .env and set your bot token."
        )

    return Settings(
        discord_token=token,
        max_file_size_mb=_env_int("MAX_FILE_SIZE_MB", 25),
        max_downloads_per_user_per_hour=_env_int("MAX_DOWNLOADS_PER_USER_PER_HOUR", 10),
        download_timeout_seconds=_env_float("DOWNLOAD_TIMEOUT_SECONDS", 120.0),
        compress_videos=_env_bool("COMPRESS_VIDEOS", True),
        allowed_channel_ids=_env_csv_ints("ALLOWED_CHANNEL_IDS"),
        ignored_channel_ids=_env_csv_ints("IGNORED_CHANNEL_IDS"),
        temp_dir=Path(os.getenv("TEMP_DIR", "/tmp/discord-video-bot")),
        log_file=Path(os.getenv("LOG_FILE", "logs/bot.log")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        delete_original_message=_env_bool("DELETE_ORIGINAL_MESSAGE", True),
        include_source_url=_env_bool("INCLUDE_SOURCE_URL", False),
        concurrent_download_limit=max(1, _env_int("CONCURRENT_DOWNLOAD_LIMIT", 3)),
    )
