"""URL extraction for video rehosting.

Known social platforms are recognized first. With generic mode enabled, any
other non-blocked http(s) URL is passed to yt-dlp (which supports 1000+ sites).
"""

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
    YOUTUBE = "youtube"
    TWITTER = "twitter"
    REDDIT = "reddit"
    TWITCH = "twitch"
    DAILYMAIL = "dailymail"
    GENERIC = "generic"  # any site yt-dlp might support


@dataclass(frozen=True, slots=True)
class MatchedURL:
    """A URL extracted from a message that may contain downloadable video."""

    url: str
    platform: Platform

    @property
    def is_known_platform(self) -> bool:
        return self.platform != Platform.GENERIC


# Hosts we never pass to yt-dlp (noise / not media). Known platforms are
# matched first; this list only affects the generic catch-all path.
_DEFAULT_DENY_HOSTS: frozenset[str] = frozenset(
    {
        "discord.com",
        "discordapp.com",
        "discord.gg",
        "cdn.discordapp.com",
        "media.discordapp.net",
        "google.com",
        "googleapis.com",
        "gstatic.com",
        "github.com",
        "gitlab.com",
        "stackoverflow.com",
        "wikipedia.org",
        "open.spotify.com",
        "spotify.com",
        "apple.com",
        "microsoft.com",
        "amazon.com",
        "docs.google.com",
        "drive.google.com",
        "notion.so",
        "tenor.com",
        "giphy.com",
    }
)

# Known video platforms (explicit patterns — higher confidence).
_PLATFORM_PATTERNS: dict[Platform, re.Pattern[str]] = {
    Platform.TIKTOK: re.compile(
        r"https?://(?:(?:www|vm|vt|m)\.)?tiktok\.com/\S+",
        re.IGNORECASE,
    ),
    Platform.INSTAGRAM: re.compile(
        r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|tv)/[A-Za-z0-9_\-]+/?(?:\?[^\s]*)?",
        re.IGNORECASE,
    ),
    Platform.FACEBOOK: re.compile(
        r"https?://(?:(?:www|m|web)\.)?facebook\.com/"
        r"(?:watch(?:/?\?|\?)|reel/|share/(?:r|v)/|[^?\s]+/videos/|video\.php\?)\S*"
        r"|https?://(?:(?:www|m)\.)?fb\.watch/\S+"
        r"|https?://(?:(?:www|m)\.)?fb\.com/(?:watch|reel|share)/\S+",
        re.IGNORECASE,
    ),
    Platform.YOUTUBE: re.compile(
        r"https?://(?:(?:www|m)\.)?youtube\.com/shorts/[A-Za-z0-9_\-]+/?(?:\?[^\s]*)?"
        r"|https?://youtu\.be/[A-Za-z0-9_\-]+/?(?:\?[^\s]*)?",
        re.IGNORECASE,
    ),
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
        r"https?://clips\.twitch\.tv/[A-Za-z0-9_\-]+(?:\?[^\s]*)?"
        r"|https?://(?:www\.)?twitch\.tv/[A-Za-z0-9_]+/clip/[A-Za-z0-9_\-]+(?:\?[^\s]*)?",
        re.IGNORECASE,
    ),
    Platform.DAILYMAIL: re.compile(
        r"https?://(?:(?:www|mol)\.)?dailymail\.(?:co\.uk|com)/\S*video\S+",
        re.IGNORECASE,
    ),
}

_GENERIC_URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}'\"“”’>"


def _clean_url(raw: str) -> str:
    url = raw.strip()
    while url and url[-1] in _TRAILING_PUNCTUATION:
        url = url[:-1]
    return url


def normalize_download_url(url: str, platform: Platform) -> str:
    """Rewrite share URLs into the form downloaders expect."""
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


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def _is_denied_for_generic(url: str, extra_deny: Iterable[str] | None = None) -> bool:
    host = _host(url)
    if not host:
        return True
    deny = set(_DEFAULT_DENY_HOSTS)
    if extra_deny:
        deny.update(h.lower().removeprefix("www.") for h in extra_deny)
    # Also deny if host ends with a denied domain (cdn.discordapp.com etc.)
    for blocked in deny:
        b = blocked.removeprefix("www.")
        if host == b or host.endswith("." + b):
            return True
    return False


def _match_known(url: str) -> MatchedURL | None:
    cleaned = _clean_url(url)
    ordered: Iterable[Platform] = (
        Platform.TIKTOK,
        Platform.INSTAGRAM,
        Platform.YOUTUBE,
        Platform.TWITTER,
        Platform.REDDIT,
        Platform.TWITCH,
        Platform.DAILYMAIL,
        Platform.FACEBOOK,
    )
    for platform in ordered:
        pattern = _PLATFORM_PATTERNS[platform]
        match = pattern.search(cleaned)
        if not match:
            continue
        matched_url = _clean_url(match.group(0))
        if matched_url == cleaned or cleaned.startswith(matched_url):
            return MatchedURL(
                url=normalize_download_url(cleaned, platform),
                platform=platform,
            )
    return None


def extract_video_urls(
    text: str,
    *,
    allow_generic: bool = True,
    extra_deny_hosts: Iterable[str] | None = None,
) -> list[MatchedURL]:
    """
    Extract unique video-ish URLs from message text.

    Known platforms first; then optional generic URLs for yt-dlp.
    """
    if not text:
        return []

    seen: set[str] = set()
    known: list[MatchedURL] = []
    generic: list[MatchedURL] = []

    for raw in _GENERIC_URL_PATTERN.findall(text):
        cleaned = _clean_url(raw)
        if not cleaned or cleaned in seen:
            continue

        matched = _match_known(cleaned)
        if matched is not None:
            seen.add(matched.url)
            known.append(matched)
            continue

        if allow_generic and not _is_denied_for_generic(cleaned, extra_deny_hosts):
            seen.add(cleaned)
            generic.append(MatchedURL(url=cleaned, platform=Platform.GENERIC))

    # Prefer known platforms; fall back to first generic candidate.
    return known if known else generic[:1]


def is_supported_url(url: str, *, allow_generic: bool = True) -> bool:
    return bool(extract_video_urls(url, allow_generic=allow_generic))


def detect_platform(url: str) -> Platform | None:
    matched = _match_known(url)
    return matched.platform if matched else None


def pretty_title(title: str | None) -> str | None:
    """Clean social/SEO titles for Discord captions."""
    if not title:
        return None
    cleaned = title.strip().replace("\n", " ")
    cleaned = re.sub(r"[#@]\w+", "", cleaned)
    cleaned = re.sub(r"[#@]+", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -_|")
    if len(cleaned) < 2:
        return None
    if cleaned.lower() in {"video", "original sound", "null", "n/a", "youtube"}:
        return None
    if len(cleaned) > 100:
        cleaned = cleaned[:97].rstrip() + "…"
    return cleaned
