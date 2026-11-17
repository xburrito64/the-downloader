"""YouTube provider: reads video and playlist links and downloads with yt-dlp.

yt-dlp is imported inside the functions that need it, so starting the app
does not pay for loading it.
"""

import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..errors import explain
from .base import DownloadOptions, Item, Progress, ProviderError, Resolved, Stopped

_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
_VIDEO_HEIGHTS = {"1080p": 1080, "720p": 720}
_PROGRESS_INTERVAL = 0.25  # seconds between progress updates sent onward
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_EXTRACT_LOCK = threading.Lock()  # see download(): keeps Deno to one copy at a time


class _QuietLogger:
    """Keeps yt-dlp from printing to the terminal; remembers the last error."""

    def __init__(self) -> None:
        self.last_error = ""

    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        self.last_error = message


def _clean_error(message: str) -> str:
    message = _ANSI.sub("", message).strip()
    message = re.sub(r"^ERROR:\s*", "", message)
    message = re.sub(r"^\[[\w:+]+\]\s*[\w-]+:\s*", "", message)  # "[youtube] <id>: "
    # yt-dlp appends advice meant for command-line users; keep the first sentence block.
    return explain(message.split("; please report", 1)[0].split("\n", 1)[0].strip())


def _thumbnail(info: dict) -> str:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbnails = info.get("thumbnails") or []
    return thumbnails[-1].get("url", "") if thumbnails else ""


def _to_item(info: dict) -> Item:
    video_id = info.get("id", "")
    return Item(
        provider="youtube",
        source_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title=info.get("title") or video_id,
        artist=info.get("uploader") or info.get("channel") or "",
        duration_seconds=int(info.get("duration") or 0),
        cover_url=_thumbnail(info),
    )


class YouTubeProvider:
    name = "youtube"

    def __init__(self, ffmpeg_path: str | None = None, deno_path: str | None = None) -> None:
        self._ffmpeg_path = ffmpeg_path
        self._deno_path = deno_path

    def handles(self, link: str) -> bool:
        try:
            return (urlparse(link.strip()).hostname or "").lower() in _HOSTS
        except ValueError:
            return False

    @staticmethod
    def _link_kind(link: str) -> str | None:
        """ "video", "playlist", or None for YouTube pages that are neither.

        Search pages and channel pages are refused on purpose: yt-dlp would
        treat them as playlists with hundreds or thousands of videos.
        """
        parsed = urlparse(link)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)
        if (parsed.hostname or "").lower() == "youtu.be":
            return "video" if path else None
        if path == "/watch":
            return "video" if "v" in query else None
        if path.startswith(("/shorts/", "/live/", "/embed/")):
            return "video"
        if path == "/playlist" and "list" in query:
            return "playlist"
        return None

    def _base_options(self, logger: _QuietLogger) -> dict:
        options = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": logger,
            "color": "never",
            "noplaylist": True,
            "js_runtimes": {"deno": {"path": self._deno_path} if self._deno_path else {}},
        }
        if self._ffmpeg_path:
            options["ffmpeg_location"] = self._ffmpeg_path
        return options

    def resolve(self, link: str) -> Resolved:
        import yt_dlp

        link = link.strip()
        logger = _QuietLogger()
        options = self._base_options(logger)
        # Flat extraction lists a playlist in one request instead of one request per video.
        options["extract_flat"] = "in_playlist"
        kind = self._link_kind(link)
        if kind is None:
            raise ProviderError("This YouTube link is not a video or a playlist. Channel and search pages are not supported.")
        # A link to a video that happens to sit in a playlist means "this video".
        # Only a real playlist link (no video ID in it) means "the whole playlist".
        options["noplaylist"] = kind == "video"

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(link, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise ProviderError(_clean_error(logger.last_error or str(exc))) from exc
        if not info:
            raise ProviderError("Nothing was found at this link.")

        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e and e.get("id")]
            # Removed and private videos are listed without usable details; leave them out.
            items = [_to_item(e) for e in entries if e.get("title") not in ("[Deleted video]", "[Private video]")]
            return Resolved(
                kind="playlist",
                title=info.get("title") or "Playlist",
                items=items,
                cover_url=_thumbnail(info) or (items[0].cover_url if items else ""),
            )
        item = _to_item(info)
        return Resolved(kind="video", title=item.title, items=[item], cover_url=item.cover_url)

    def download(
        self,
        item: Item,
        options: DownloadOptions,
        on_progress: Callable[[Progress], None],
        should_stop: Callable[[], bool],
    ) -> Path:
        import yt_dlp

        logger = _QuietLogger()
        ydl_options = self._base_options(logger)
        options.target.parent.mkdir(parents=True, exist_ok=True)
        # "%" has a special meaning in yt-dlp's output template, so it is doubled.
        ydl_options["outtmpl"] = str(options.target).replace("%", "%%") + ".%(ext)s"
        ydl_options["overwrites"] = False

        if options.mode == "audio":
            ydl_options["format"] = "bestaudio/best"
            if options.audio_format == "mp3":
                codec = {"preferredcodec": "mp3", "preferredquality": "192"}
            else:
                # "best" copies the audio stream out unchanged: no re-encoding, no quality loss.
                codec = {"preferredcodec": "best"}
            ydl_options["postprocessors"] = [{"key": "FFmpegExtractAudio", **codec}]
        else:
            ydl_options["format"] = "bestvideo*+bestaudio/best"
            height = _VIDEO_HEIGHTS.get(options.video_quality)
            if height:
                # 1080p and 720p: take the largest picture up to that size, and prefer the
                # streams that fit a normal .mp4, which plays everywhere.
                ydl_options["format_sort"] = [f"res:{height}", "ext:mp4:m4a"]
            # "best" takes the highest quality YouTube has, whatever the file type (often .mkv).
            # Joining picture and sound is a copy, not a re-encode. mp4 when possible, mkv otherwise.
            ydl_options["merge_output_format"] = "mp4/mkv"

        state = {"finished_bytes": 0, "last_sent": 0.0}

        def progress_hook(d: dict) -> None:
            if should_stop():
                raise yt_dlp.utils.DownloadCancelled("stopped")
            status = d.get("status")
            if status == "finished":
                state["finished_bytes"] += d.get("total_bytes") or d.get("downloaded_bytes") or 0
                return
            if status != "downloading":
                return
            now = time.monotonic()
            if now - state["last_sent"] < _PROGRESS_INTERVAL:
                return
            state["last_sent"] = now

            downloaded = d.get("downloaded_bytes") or 0
            file_total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            # A video is two files (picture and sound). Use their combined size when known,
            # so the bar runs once from 0 to 100 instead of twice.
            parts = (d.get("info_dict") or {}).get("requested_formats") or []
            sizes = [p.get("filesize") or p.get("filesize_approx") or 0 for p in parts]
            if sizes and all(sizes):
                fraction = (state["finished_bytes"] + downloaded) / sum(sizes)
            elif file_total:
                fraction = downloaded / file_total
            else:
                fraction = 0.0
            on_progress(Progress(min(fraction, 1.0), float(d.get("speed") or 0.0), "downloading"))

        def postprocessor_hook(d: dict) -> None:
            if should_stop():
                raise yt_dlp.utils.DownloadCancelled("stopped")
            if d.get("status") == "started":
                on_progress(Progress(1.0, 0.0, "converting"))

        ydl_options["progress_hooks"] = [progress_hook]
        ydl_options["postprocessor_hooks"] = [postprocessor_hook]

        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                # Reading a video's details starts Deno, which takes up to 300 MB for a
                # second or two. Only one download does this at a time; the downloading
                # itself, which is the slow part, still runs in parallel.
                while not _EXTRACT_LOCK.acquire(timeout=0.5):
                    if should_stop():
                        raise Stopped()
                try:
                    info = ydl.extract_info(item.url, download=False)
                finally:
                    _EXTRACT_LOCK.release()
                if should_stop():
                    raise Stopped()
                info = ydl.process_ie_result(info, download=True)
        except yt_dlp.utils.DownloadCancelled as exc:
            raise Stopped() from exc
        except yt_dlp.utils.DownloadError as exc:
            raise ProviderError(_clean_error(logger.last_error or str(exc))) from exc

        downloads = (info or {}).get("requested_downloads") or []
        filepath = downloads[0].get("filepath") if downloads else None
        if not filepath or not Path(filepath).is_file():
            raise ProviderError("The download finished but the file could not be found.")
        return Path(filepath)
