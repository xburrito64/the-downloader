"""Turns a naming template and an item into a safe file path."""

import re
from pathlib import Path, PurePosixPath

from .providers.base import Item

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_MAX_PART_LENGTH = 120


def safe_name(text: str) -> str:
    """Make text usable as one Windows file or folder name."""
    name = _FORBIDDEN.sub("_", text)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name[:_MAX_PART_LENGTH].rstrip(" .")
    if not name:
        return "untitled"
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name


def render(template: str, item: Item) -> Path:
    """Fill a template like "{artist}/{album}/{track} - {title}" for one item.

    Returns a relative path without file extension. Each folder level is
    sanitised on its own, so a "/" inside a title can never create a folder.
    """
    values = {
        "title": item.title or "untitled",
        "artist": item.artist or "Unknown artist",
        "album": item.album or "Unknown album",
        "track": f"{item.track_number:02d}" if item.track_number else "",
        "id": item.source_id,
    }
    parts = []
    for raw_part in PurePosixPath(template.replace("\\", "/")).parts:
        if raw_part in ("/", "..", "."):
            continue
        filled = re.sub(r"\{(\w+)\}", lambda m: _FORBIDDEN.sub("_", values.get(m.group(1), m.group(0))), raw_part)
        # An empty {track} leaves a dangling separator such as " - Title"; tidy it.
        filled = re.sub(r"^[\s\-_.]+", "", filled)
        parts.append(safe_name(filled))
    return Path(*parts) if parts else Path(safe_name(values["title"]))
