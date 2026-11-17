"""SoundCloud tracks pasted into Other match, for Spotify songs that YouTube does not have.

The app never searches SoundCloud by itself. SoundCloud is full of reuploads, sped-up
copies and remixes under the same name, so only a link the user pasted is read. The
audio is then downloaded like a YouTube recording and tagged from Spotify.
"""

import re

from ..matching import Candidate, score
from .base import Item, ProviderError
from .youtube import _QuietLogger

# A track page: soundcloud.com/<artist>/<track>, with an "s-..." part for a private link.
_TRACK = re.compile(r"^(?:https?://)?(?:(?:www|m)\.)?soundcloud\.com/([\w-]+)/([\w-]+)(/s-[\w-]+)?/?(?:[?#].*)?$")
# The short links the SoundCloud app shares.
_SHORT = re.compile(r"^(?:https?://)?on\.soundcloud\.com/([\w-]+)/?(?:[?#].*)?$")
# Pages under an artist that are not a single track.
_NOT_TRACKS = {"sets", "tracks", "albums", "reposts", "likes", "popular-tracks", "comments", "spotlight",
               "followers", "following", "toptracks"}
# What a picked match is kept as. Built by this module only, and checked again wherever it arrives.
_STORED = re.compile(r"^https://soundcloud\.com/[\w-]+/[\w-]+(?:/s-[\w-]+)?$")

PREVIEW_ONLY = ("SoundCloud only plays a 30-second preview of this track to people without SoundCloud Go+, "
                "so it cannot be downloaded.")


def link_in(text: str) -> str:
    """The SoundCloud track link in what was pasted, as a clean https address, else ""."""
    text = text.strip()
    track = _TRACK.match(text)
    if track and track.group(2) not in _NOT_TRACKS:
        return f"https://soundcloud.com/{track.group(1)}/{track.group(2)}{track.group(3) or ''}"
    short = _SHORT.match(text)
    return f"https://on.soundcloud.com/{short.group(1)}" if short else ""


def is_track(match_id: str) -> bool:
    """True for a SoundCloud match as the app stores it."""
    return bool(_STORED.match(match_id))


def candidate(item: Item, link: str) -> Candidate:
    """Read a pasted SoundCloud track and score it against the Spotify song."""
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
                               "color": "never", "logger": _QuietLogger()}) as ydl:
            info = ydl.extract_info(link, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise ProviderError("SoundCloud could not open this link. Check that it is a single track and still online.") from exc

    # A short link turns into the track's own address; keep that one, without anything after "?".
    address = (info.get("webpage_url") or "").split("?", 1)[0].rstrip("/").replace("://www.", "://").replace("://m.", "://")
    if info.get("extractor") != "soundcloud" or not is_track(address):
        raise ProviderError("This SoundCloud link is not a single track.")
    formats = info.get("formats") or []
    if formats and all("preview" in (f.get("format_id") or "") for f in formats):
        raise ProviderError(PREVIEW_ONLY)

    artists = [name for name in [*(info.get("artists") or []), info.get("uploader")] if name]
    title = info.get("title") or ""
    duration = round(info.get("duration") or 0)
    return Candidate(
        video_id=address,
        title=title,
        artist=", ".join(dict.fromkeys(artists)),
        album="",
        duration_seconds=duration,
        kind="soundcloud",
        # Anyone can upload to SoundCloud, so it is scored like a YouTube video.
        score=score(item, title, artists, duration, "video"),
        cover_url=info.get("thumbnail") or "",
    )
