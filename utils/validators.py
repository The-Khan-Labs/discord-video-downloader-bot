"""URL validation and platform detection for supported social video sites."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable
from urllib.parse import urlparse


class Platform(str, Enum):
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    YOUTUBE_SHORTS = "youtube_shorts"
    TWITTER = "twitter"
    REDDIT = "reddit"
    TWITCH = "twitch"
    DAILYMAIL = "dailymail"


@dataclass(frozen=True, slots=True)
class MatchedURL:
    """A URL extracted from a message that matches a supported platform."""

    url: str
    platform: Platform


# Patterns intentionally cover common share/short link forms used in Discord.
_PLATFORM_PATTERNS: dict[Platform, re.Pattern[str]] = {
    Platform.TIKTOK: re.compile(
        r"https?://(?:(?:www|vm|vt|m)\.)?tiktok\.com/\S+",
        re.IGNORECASE,
    ),
    Platform.INSTAGRAM: re.compile(
        r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|tv)/[A-Za-z0-9_\-]+/?(?:\?[^\s]*)?",
        re.IGNORECASE,
    ),
    # Video-ish Facebook URLs only (not random profile/page links).
    Platform.FACEBOOK: re.compile(
        r"https?://(?:(?:www|m|web)\.)?facebook\.com/"
        r"(?:watch(?:/?\?|\?)|reel/|share/(?:r|v)/|[^?\s]+/videos/|video\.php\?)\S*"
        r"|https?://(?:(?:www|m)\.)?fb\.watch/\S+"
        r"|https?://(?:(?:www|m)\.)?fb\.com/(?:watch|reel|share)/\S+",
        re.IGNORECASE,
    ),
    Platform.YOUTUBE_SHORTS: re.compile(
        r"https?://(?:(?:www|m)\.)?youtube\.com/shorts/[A-Za-z0-9_\-]+/?(?:\?[^\s]*)?"
        r"|https?://youtu\.be/[A-Za-z0-9_\-]+/?(?:\?[^\s]*)?",
        re.IGNORECASE,
    ),
    # Includes mobile share forms: /status/ID/video/1?s=46
    Platform.TWITTER: re.compile(
        r"https?://(?:(?:www|mobile)\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+/status/\d+"
        r"(?:/(?:video|photo)/\d+)?/?(?:\?[^\s]*)?",
        re.IGNORECASE,
    ),
    Platform.REDDIT: re.compile(
        r"https?://(?:(?:www|old|new|m|np)\.)?reddit\.com/r/[A-Za-z0-9_]+/comments/\S+"
        r"|https?://(?:v\.)?redd\.it/\S+",
        re.IGNORECASE,
    ),
    Platform.TWITCH: re.compile(
        r"https?://(?:(?:www|m|clips)\.)?twitch\.tv/(?:[A-Za-z0-9_]+/clip/|clips\.twitch\.tv/)?"
        r"[A-Za-z0-9_\-]+(?:\?[^\s]*)?",
        re.IGNORECASE,
    ),
    # e.g. dailymail.com/video/.../video-3567493/...html
    Platform.DAILYMAIL: re.compile(
        r"https?://(?:(?:www|mol)\.)?dailymail\.(?:co\.uk|com)/\S*video\S+",
        re.IGNORECASE,
    ),
}

# Combined pattern used to pull candidate URLs out of free-form message text.
_GENERIC_URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)

# Trailing punctuation Discord users often leave after pasted links.
_TRAILING_PUNCTUATION = ".,;:!?)]}'\"“”’>"


def _clean_url(raw: str) -> str:
    url = raw.strip()
    while url and url[-1] in _TRAILING_PUNCTUATION:
        url = url[:-1]
    return url


def normalize_download_url(url: str, platform: Platform) -> str:
    """
    Rewrite share URLs into the form downloaders expect.

    X/Twitter mobile links often look like .../status/ID/video/1?s=46
    """
    cleaned = _clean_url(url)
    if platform == Platform.TWITTER:
        match = re.search(
            r"(https?://(?:(?:www|mobile)\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+/status/\d+)",
            cleaned,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
    return cleaned


def _normalize_platform_match(url: str) -> MatchedURL | None:
    cleaned = _clean_url(url)
    if not cleaned:
        return None

    # Prefer more specific platforms first to avoid Facebook false positives, etc.
    ordered_platforms: Iterable[Platform] = (
        Platform.TIKTOK,
        Platform.INSTAGRAM,
        Platform.YOUTUBE_SHORTS,
        Platform.TWITTER,
        Platform.REDDIT,
        Platform.TWITCH,
        Platform.DAILYMAIL,
        Platform.FACEBOOK,
    )

    for platform in ordered_platforms:
        pattern = _PLATFORM_PATTERNS[platform]
        match = pattern.search(cleaned)
        if not match:
            continue
        # Accept fullmatch OR when the pattern is a prefix of the cleaned URL
        # (covers extra junk Discord sometimes appends).
        matched_url = _clean_url(match.group(0))
        if matched_url == cleaned or cleaned.startswith(matched_url):
            final_url = normalize_download_url(cleaned, platform)
            return MatchedURL(url=final_url, platform=platform)

    return None


def is_supported_url(url: str) -> bool:
    """Return True if the URL belongs to a supported video platform."""
    return _normalize_platform_match(url) is not None


def detect_platform(url: str) -> Platform | None:
    """Return the platform for a URL, or None if unsupported."""
    matched = _normalize_platform_match(url)
    return matched.platform if matched else None


def extract_video_urls(text: str) -> list[MatchedURL]:
    """
    Extract unique supported video URLs from message text.

    Order of first appearance is preserved.
    """
    if not text:
        return []

    seen: set[str] = set()
    results: list[MatchedURL] = []

    for raw in _GENERIC_URL_PATTERN.findall(text):
        cleaned = _clean_url(raw)
        if cleaned in seen:
            continue
        matched = _normalize_platform_match(cleaned)
        if matched is None:
            continue
        # Extra host sanity check for twitch generic path noise
        if matched.platform == Platform.TWITCH and not _is_twitch_clip(matched.url):
            continue
        seen.add(matched.url)
        results.append(matched)

    return results


def _is_twitch_clip(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if "clips.twitch.tv" in host:
        return True
    if "twitch.tv" in host and "/clip/" in path:
        return True
    return False
