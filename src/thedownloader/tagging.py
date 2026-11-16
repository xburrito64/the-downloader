"""Writes title, artist, album, track number, year and cover art into audio files."""

import base64
from pathlib import Path

from .providers.base import Item


class TaggingError(Exception):
    pass


def fetch_cover(url: str) -> bytes | None:
    """Download cover art. A missing cover is not an error; the file is tagged without it."""
    if not url:
        return None
    import requests

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None
    # Guard against something that is clearly not a normal cover image.
    return response.content if 0 < len(response.content) <= 10 * 1024 * 1024 else None


def _mime(image: bytes) -> str:
    return "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"


def _tag_opus(path: Path, item: Item, cover: bytes | None) -> None:
    from mutagen.flac import Picture
    from mutagen.oggopus import OggOpus

    audio = OggOpus(path)
    audio["title"] = item.title
    audio["artist"] = item.artist.split(", ") if item.artist else []
    if item.album:
        audio["album"] = item.album
    if item.track_number:
        audio["tracknumber"] = str(item.track_number)
    if item.year:
        audio["date"] = item.year
    if item.isrc:
        audio["isrc"] = item.isrc
    if cover:
        picture = Picture()
        picture.type = 3  # front cover
        picture.mime = _mime(cover)
        picture.data = cover
        audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
    audio.save()


def _tag_m4a(path: Path, item: Item, cover: bytes | None) -> None:
    from mutagen.mp4 import MP4, MP4Cover

    audio = MP4(path)
    audio["\xa9nam"] = item.title
    if item.artist:
        audio["\xa9ART"] = item.artist
    if item.album:
        audio["\xa9alb"] = item.album
    if item.track_number:
        audio["trkn"] = [(item.track_number, 0)]
    if item.year:
        audio["\xa9day"] = item.year
    if cover:
        image_format = MP4Cover.FORMAT_PNG if _mime(cover) == "image/png" else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(cover, imageformat=image_format)]
    audio.save()


def _tag_mp3(path: Path, item: Item, cover: bytes | None) -> None:
    from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TRCK, TSRC, ID3NoHeaderError

    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.setall("TIT2", [TIT2(encoding=3, text=item.title)])
    if item.artist:
        tags.setall("TPE1", [TPE1(encoding=3, text=item.artist.split(", "))])
    if item.album:
        tags.setall("TALB", [TALB(encoding=3, text=item.album)])
    if item.track_number:
        tags.setall("TRCK", [TRCK(encoding=3, text=str(item.track_number))])
    if item.year:
        tags.setall("TDRC", [TDRC(encoding=3, text=item.year)])
    if item.isrc:
        tags.setall("TSRC", [TSRC(encoding=3, text=item.isrc)])
    if cover:
        tags.setall("APIC", [APIC(encoding=3, mime=_mime(cover), type=3, desc="Cover", data=cover)])
    tags.save(path)


_WRITERS = {".opus": _tag_opus, ".ogg": _tag_opus, ".m4a": _tag_m4a, ".mp3": _tag_mp3}


def tag(path: Path, item: Item, cover: bytes | None) -> None:
    writer = _WRITERS.get(path.suffix.lower())
    if writer is None:
        raise TaggingError(f"Tagging {path.suffix} files is not supported.")
    try:
        writer(path, item, cover)
    except Exception as exc:  # mutagen raises many unrelated error types
        raise TaggingError(f"Could not write tags: {exc}") from exc
