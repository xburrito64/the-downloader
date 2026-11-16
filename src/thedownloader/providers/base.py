"""The one interface every source (YouTube, Spotify, later others) implements.

The core queue and the UI only ever talk to this interface, so adding a source
means adding one module and touching nothing else.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Item:
    """One downloadable thing: a single video or a single track."""

    provider: str  # "youtube" or "spotify"
    source_id: str  # YouTube video ID or Spotify track ID; used to skip duplicates
    url: str
    title: str
    artist: str = ""
    album: str = ""
    duration_seconds: int = 0
    cover_url: str = ""
    track_number: int = 0
    year: str = ""
    isrc: str = ""  # international recording code; helps find the exact same recording
    # Spotify only: the YouTube video chosen as the audio source. Empty means "pick the best match".
    match_id: str = ""


@dataclass
class Resolved:
    """What a pasted link turned out to be, for the preview."""

    kind: str  # "video", "track", "album" or "playlist"
    title: str
    items: list[Item] = field(default_factory=list)
    cover_url: str = ""


@dataclass
class DownloadOptions:
    mode: str  # "audio" or "video"
    audio_format: str  # "original" or "mp3"
    video_quality: str  # "best", "1080p" or "720p"
    target: Path  # full path without file extension


@dataclass
class Progress:
    fraction: float  # 0.0 to 1.0
    speed_bytes_per_second: float = 0.0
    stage: str = "downloading"  # "downloading", "converting" or "tagging"


class ProviderError(Exception):
    """A link could not be read or an item could not be downloaded.

    The message is written for the user and shown as-is.
    """


class Stopped(Exception):
    """The download was stopped on request (pause or cancel). Partial files are kept."""


class Provider(Protocol):
    name: str

    def handles(self, link: str) -> bool:
        """True when this provider recognises the link."""
        ...

    def resolve(self, link: str) -> Resolved:
        """Read what the link contains, without downloading anything."""
        ...

    def download(
        self,
        item: Item,
        options: DownloadOptions,
        on_progress: Callable[[Progress], None],
        should_stop: Callable[[], bool],
    ) -> Path:
        """Download one item and return the finished file's path.

        Calls on_progress as it goes and stops early when should_stop() returns True.
        """
        ...
