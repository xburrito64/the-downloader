"""Settings: one JSON file, loaded over built-in defaults.

Unknown keys in the file are ignored and missing keys fall back to defaults,
so the file keeps working when settings are added or removed in later versions.
"""

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import paths


@dataclass
class Settings:
    # Where downloads go: <output_dir>/<youtube_subdir or spotify_subdir>/<template>
    output_dir: str = field(default_factory=lambda: str(paths.default_output_dir()))
    youtube_subdir: str = "YouTube"
    spotify_subdir: str = "Spotify"
    youtube_template: str = "{title}"
    spotify_template: str = "{artist} - {title}"
    # A playlist or album goes into a folder with its name: <subdir>/<playlist name>/<template>
    playlist_folders: bool = True

    # Last-used choices, remembered between sessions
    mode: str = "audio"  # "audio" or "video"
    audio_format: str = "original"  # "original" (no re-encoding) or "mp3"
    video_quality: str = "best"  # "best", "1080p" or "720p"

    max_parallel_downloads: int = 2

    # Leave empty to find the programs automatically
    ffmpeg_path: str = ""
    deno_path: str = ""

    spotify_client_id: str = ""

    # Turns the game-like motion in the window into plain instant changes
    reduce_motion: bool = False

    def output_path(self, provider: str) -> Path:
        sub = self.spotify_subdir if provider == "spotify" else self.youtube_subdir
        return Path(self.output_dir) / sub


def load(file: Path | None = None) -> Settings:
    file = file or paths.config_file()
    try:
        # utf-8-sig also accepts files saved by Notepad or PowerShell, which add a hidden marker.
        raw = json.loads(file.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return Settings()
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"Could not read settings file {file}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Settings file {file} does not contain a JSON object.")

    known = {f.name: f.type for f in fields(Settings)}
    values = {}
    for key, value in raw.items():
        expected = known.get(key)
        # Skip unknown keys and values of the wrong type; the default is used instead.
        # (In Python True counts as a number, so yes/no values are checked separately.)
        if expected is not None and isinstance(value, expected) and isinstance(value, bool) == (expected is bool):
            values[key] = value
    return Settings(**values)


def save(settings: Settings, file: Path | None = None) -> None:
    file = file or paths.config_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file first so a crash can never leave a half-written config.
    tmp = file.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    os.replace(tmp, file)


class ConfigError(Exception):
    pass
