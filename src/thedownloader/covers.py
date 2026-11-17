"""Small cover pictures for the UI, kept on disk.

Spotify and YouTube hand out covers that are far bigger than a card on screen.
Showing those directly would cost the window megabytes of memory per picture,
so each cover is shrunk once and the small copy is reused from then on.

The shrinking is done by ffmpeg, which is installed anyway. That avoids adding
an image library to the engine just for this.
"""

import hashlib
import os
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit

from . import paths

SIZE = 256        # pixels, square. Cards are 140 wide; this stays sharp on a high-DPI screen.
WIDE = (384, 216)  # the 16:9 shape used for videos
_ALLOWED_DOMAINS = ("scdn.co", "spotifycdn.com", "ytimg.com", "ggpht.com", "googleusercontent.com", "sndcdn.com")
_MAX_DOWNLOAD_BYTES = 5_000_000
_MAX_FILES = 4000
_slots = threading.Semaphore(2)  # at most two covers are fetched and shrunk at a time


def folder() -> Path:
    return paths.data_dir() / "covers"


def allowed(url: str) -> bool:
    """Only picture servers of Spotify and YouTube are ever contacted.

    The address comes from the UI, so without this check the engine could be
    asked to fetch anything, including addresses inside the home network.
    """
    if len(url) > 2000:
        return False
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or port not in (None, 443) or parts.username or parts.password:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in _ALLOWED_DOMAINS)


def _kind(data: bytes) -> str | None:
    """Which ffmpeg reader to use. Decided from the file's first bytes, never guessed by ffmpeg.

    Letting ffmpeg guess would let a server send a playlist-like file that makes ffmpeg
    open other files or addresses.
    """
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg_pipe"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png_pipe"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp_pipe"
    return None


def _fetch(url: str) -> bytes | None:
    import requests

    try:
        with requests.get(url, timeout=10, stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                return None
            data = response.raw.read(_MAX_DOWNLOAD_BYTES + 1, decode_content=True)
    except requests.RequestException:
        return None
    return data if 0 < len(data) <= _MAX_DOWNLOAD_BYTES else None


def thumbnail(url: str, ffmpeg_path: str | None, wide: bool = False) -> Path | None:
    """The small copy of a cover, made on first use. None when it cannot be made.

    Square by default (album covers). wide gives the 16:9 shape of a video picture; cutting
    to that shape also removes the black bars YouTube adds to its 4:3 pictures.
    """
    if not allowed(url):
        return None
    width, height = WIDE if wide else (SIZE, SIZE)
    name = hashlib.sha256(url.encode()).hexdigest()[:32] + ("-wide" if wide else "")
    target = folder() / (name + ".jpg")
    if target.is_file():
        return target
    if not ffmpeg_path:
        return None
    with _slots:
        if target.is_file():  # another request made it while this one waited
            return target
        data = _fetch(url)
        kind = _kind(data) if data else None
        if kind is None:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.stem}.{threading.get_ident()}.tmp")
        crop = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        try:
            result = subprocess.run(
                [ffmpeg_path, "-v", "error", "-nostdin", "-y", "-f", kind, "-i", "pipe:0",
                 "-vf", crop, "-frames:v", "1", "-q:v", "4", "-f", "mjpeg", str(temporary)],
                input=data, capture_output=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
                return None
            os.replace(temporary, target)
        except (OSError, subprocess.TimeoutExpired):
            return None
        finally:
            temporary.unlink(missing_ok=True)
    return target


def prune() -> int:
    """Keep the folder from growing forever: beyond the limit, the oldest pictures go."""
    try:
        files = sorted(folder().glob("*.jpg"), key=lambda f: f.stat().st_mtime)
    except OSError:
        return 0
    removed = 0
    for old in files[: max(0, len(files) - _MAX_FILES)]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    return removed
