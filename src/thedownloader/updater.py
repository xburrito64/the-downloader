"""Checks GitHub for a newer version and installs it, without opening GitHub.

The app is installed as a git copy of its GitHub repository, so "is there an update"
means "does GitHub have commits this copy does not". Installing one means: get them,
bring the Python parts up to date (uv), and rebuild the window's screens (npm).

That cannot happen while the app runs, because Windows will not replace files that
are in use. So the app writes a small PowerShell script, starts it in a window of its
own and closes. The script waits for the app to be gone, updates, and opens the app
again. If something fails, its window stays open and says what went wrong.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from . import paths

BRANCH = "main"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class UpdateError(Exception):
    pass


def project_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _git(*args: str, timeout: int = 30, folder: Path | None = None) -> str:
    git = shutil.which("git")
    if not git:
        raise UpdateError("Git is not installed, so the app cannot look for updates. Install it with: winget install Git.Git")
    try:
        result = subprocess.run([git, *args], cwd=folder or project_dir(), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise UpdateError("GitHub did not answer in time. Check your internet, then try again.") from None
    if result.returncode != 0:
        raise UpdateError(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "git failed.")
    return result.stdout.strip()


def _number(folder: Path) -> str:
    """The version number from pyproject.toml, for example "1.0.0"."""
    import tomllib

    try:
        return tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, ValueError):
        return ""


def version(folder: Path | None = None) -> dict:
    """The installed version: its number, and the short commit name and date of this copy."""
    folder = folder or project_dir()
    number = _number(folder)
    if not (folder / ".git").exists():
        return {"number": number, "commit": "", "date": "", "git": False}
    commit, date = _git("log", "-1", "--format=%h %cs", folder=folder).split(" ", 1)
    return {"number": number, "commit": commit, "date": date, "git": True}


def check(folder: Path | None = None) -> dict:
    """Ask GitHub whether there is something newer. Changes nothing in the app's files."""
    folder = folder or project_dir()
    if not (folder / ".git").exists():
        raise UpdateError("This copy of the app was not installed with git, so it cannot update itself.")
    try:
        _git("fetch", "--quiet", "origin", BRANCH, timeout=60, folder=folder)
    except UpdateError as exc:
        if "resolve host" in str(exc).lower() or "unable to access" in str(exc).lower():
            raise UpdateError("GitHub could not be reached. Check your internet, then try again.") from None
        raise
    remote = f"origin/{BRANCH}"
    behind = int(_git("rev-list", "--count", f"HEAD..{remote}", folder=folder) or 0)
    ahead = int(_git("rev-list", "--count", f"{remote}..HEAD", folder=folder) or 0)
    changes = _git("log", "--format=%s", "--max-count=30", f"HEAD..{remote}", folder=folder)
    edited = [line[3:] for line in _git("status", "--porcelain", "--untracked-files=no", folder=folder).splitlines()]
    latest_commit, latest_date = _git("log", "-1", "--format=%h %cs", remote, folder=folder).split(" ", 1)

    reason = ""
    if behind and ahead:
        reason = "This copy has its own commits that GitHub does not have, so it cannot be updated automatically."
    elif behind and edited:
        reason = "Some of the app's files were changed on this PC (" + ", ".join(edited[:3]) + "). Undo those changes first."
    return {
        **version(folder),
        "latest_commit": latest_commit,
        "latest_date": latest_date,
        "behind": behind,
        "changes": [line for line in changes.splitlines() if line.strip()],
        "can_update": bool(behind) and not reason,
        "reason": reason,
    }


_SCRIPT = r"""
param([int]$AppPid, [string]$Project, [string]$Python)
$Host.UI.RawUI.WindowTitle = 'Updating THE Downloader'
$ErrorActionPreference = 'Stop'
function Step($text) { Write-Host ''; Write-Host "  $text" -ForegroundColor Green }
function Run($exe, [string[]]$arguments) {
  & $exe @arguments
  if ($LASTEXITCODE -ne 0) { throw "'$exe $($arguments -join ' ')' did not finish (exit code $LASTEXITCODE)." }
}
try {
  Write-Host ''
  Write-Host '  THE Downloader is updating. This window closes by itself when it is done.'
  Step 'Waiting for the app to close'
  try { Wait-Process -Id $AppPid -Timeout 60 -ErrorAction Stop } catch { }
  Start-Sleep -Seconds 2
  Set-Location -LiteralPath $Project
  Step 'Getting the new version from GitHub'
  Run 'git' @('pull', '--ff-only', 'origin', 'main')
  Step 'Updating the engine'
  Run 'uv' @('sync')
  Step 'Rebuilding the screens'
  Set-Location -LiteralPath (Join-Path $Project 'ui')
  Run 'npm' @('ci', '--no-audit', '--no-fund')
  Run 'npm' @('run', 'build')
  Step 'Done. Opening the app again.'
  Start-Process -FilePath $Python -ArgumentList '-m', 'thedownloader.window' -WorkingDirectory $Project
  Start-Sleep -Seconds 2
} catch {
  Write-Host ''
  Write-Host "  The update did not finish: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host '  Your downloads and settings are untouched. Open the app as usual and try again later,'
  Write-Host '  or run "git pull", "uv sync", then "npm ci" and "npm run build" in the ui folder.'
  Read-Host '  Press Enter to close this window'
}
"""


def start_update(app_pid: int) -> None:
    """Start the update in its own window. The app must close right after this."""
    status = check()
    if not status["can_update"]:
        raise UpdateError(status["reason"] or "You already have the newest version.")
    missing = [name for name in ("git", "uv", "npm") if not shutil.which(name)]
    if missing:
        raise UpdateError(f"{' and '.join(missing)} cannot be found, so the update cannot run.")
    python = Path(sys.executable).with_name("pythonw.exe")
    script = paths.data_dir() / "update.ps1"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_SCRIPT, encoding="utf-8-sig")
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-AppPid", str(app_pid), "-Project", str(project_dir()), "-Python", str(python)],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
