"""Where the app keeps its own files. Nothing here lives inside the repo."""

import os
from pathlib import Path

from . import APP_NAME


def config_dir() -> Path:
    """Settings and the Spotify login token (roams with the Windows profile)."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_NAME


def data_dir() -> Path:
    """History database and cover thumbnails (stays on this PC)."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def config_file() -> Path:
    return config_dir() / "config.json"


def spotify_token_file() -> Path:
    return config_dir() / "spotify.token"


def default_output_dir() -> Path:
    return Path.home() / "Downloads" / APP_NAME
