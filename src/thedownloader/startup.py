"""Startup check: are the programs and logins the app depends on in place?

Each check returns a plain result the UI (or the terminal) can display.
Nothing here imports yt-dlp itself, so the check stays fast.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from . import paths
from .config import Settings


@dataclass
class Check:
    name: str
    ok: bool
    detail: str  # version or location when ok, what is wrong when not
    fix: str = ""  # how to fix it, shown only when not ok
    required: bool = True


def _current_windows_path() -> str:
    """The PATH as Windows has it stored right now.

    A running program keeps the PATH it was started with, so a tool installed
    a minute ago is invisible to it. Reading the stored value finds it anyway.
    """
    try:
        import winreg
    except ImportError:  # not on Windows
        return ""
    locations = [
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ]
    parts = []
    for root, key_name in locations:
        try:
            with winreg.OpenKey(root, key_name) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        parts.append(os.path.expandvars(value))
    return os.pathsep.join(parts)


def find_program(name: str, configured: str = "") -> str | None:
    if configured:
        return configured if Path(configured).is_file() else None
    return shutil.which(name) or shutil.which(name, path=_current_windows_path())


def _first_line(program: str, arg: str) -> str:
    try:
        result = subprocess.run(
            [program, arg],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if result.returncode != 0:
        raise RuntimeError(f"exited with code {result.returncode}")
    lines = (result.stdout or result.stderr).strip().splitlines()
    return lines[0] if lines else ""


def _check_program(label: str, name: str, configured: str, version_arg: str, fix: str) -> Check:
    program = find_program(name, configured)
    if program is None:
        detail = f"not found at {configured}" if configured else "not installed"
        return Check(label, False, detail, fix)
    try:
        version = _first_line(program, version_arg)
    except RuntimeError as exc:
        return Check(label, False, f"found at {program} but could not run: {exc}", fix)
    return Check(label, True, f"{version}  ({program})")


def check_ffmpeg(settings: Settings) -> Check:
    return _check_program(
        "ffmpeg",
        "ffmpeg",
        settings.ffmpeg_path,
        "-version",
        "Install with: winget install Gyan.FFmpeg   (then restart the app)",
    )


def check_deno(settings: Settings) -> Check:
    return _check_program(
        "Deno",
        "deno",
        settings.deno_path,
        "--version",
        "Install with: winget install DenoLand.Deno   (then restart the app)",
    )


def check_ytdlp() -> Check:
    fix = "Run: uv sync"
    try:
        version = metadata.version("yt-dlp")
    except metadata.PackageNotFoundError:
        return Check("yt-dlp", False, "not installed", fix)
    try:
        ejs = metadata.version("yt-dlp-ejs")
    except metadata.PackageNotFoundError:
        return Check("yt-dlp", False, f"{version}, but yt-dlp-ejs is missing", fix)
    return Check("yt-dlp", True, f"{version}  (yt-dlp-ejs {ejs})")


def check_spotify(settings: Settings) -> Check:
    # Spotify is optional: YouTube downloads work without it.
    if not settings.spotify_client_id:
        return Check(
            "Spotify",
            False,
            "no client ID set",
            "Create an app in the Spotify developer dashboard and add its client ID in Settings.",
            required=False,
        )
    if not paths.spotify_token_file().is_file():
        return Check("Spotify", False, "not logged in", "Log in to Spotify from Settings.", required=False)
    return Check("Spotify", True, "client ID set, logged in", required=False)


def run_checks(settings: Settings) -> list[Check]:
    return [check_ffmpeg(settings), check_deno(settings), check_ytdlp(), check_spotify(settings)]
