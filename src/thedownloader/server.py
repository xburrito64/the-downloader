"""Starts the local API server. Used by the terminal now and by the app window later."""

import secrets
import socket
from pathlib import Path

from . import config, covers, startup
from .api import AppState, create_app
from .store import Store


def build_state(token: str | None = None) -> AppState:
    from .providers.spotify import SpotifyProvider
    from .providers.youtube import YouTubeProvider

    settings = config.load()
    ffmpeg = startup.find_program("ffmpeg", settings.ffmpeg_path)
    youtube = YouTubeProvider(
        ffmpeg_path=ffmpeg,
        deno_path=startup.find_program("deno", settings.deno_path),
        settings=settings,
    )
    providers = [SpotifyProvider(settings.spotify_client_id, youtube), youtube]
    covers.prune()
    return AppState(settings, Store(), providers, token or secrets.token_urlsafe(32),
                    ffmpeg_path=ffmpeg, ui_dir=ui_dir())


def ui_dir() -> Path:
    """Where the built UI files are (made by `npm run build` in the ui folder)."""
    return Path(__file__).resolve().parents[2] / "ui" / "dist"


def open_socket(port: int = 0) -> socket.socket:
    """A listening socket on this PC only. Port 0 means "any free port"."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    return sock


def make_server(state: AppState):
    import uvicorn

    # No access log: one line per request would be written for every progress poll and is never read.
    # timeout_graceful_shutdown: an event stream that is still open when the server is asked
    # to stop (for example on Ctrl+C) is cut after 3 seconds instead of blocking the shutdown.
    server_config = uvicorn.Config(create_app(state), log_level="warning", access_log=False, timeout_graceful_shutdown=3)
    return uvicorn.Server(server_config)


def stop(server, state: AppState) -> None:
    """Ask the server to shut down from another thread. Event streams are ended first, so it is immediate."""
    state.hub.close()
    server.should_exit = True


def serve(port: int = 0) -> None:
    """Run until Ctrl+C."""
    state = build_state()
    sock = open_socket(port)
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    print(f"API running at {address}")
    print(f"Token: {state.token}")
    print("Press Ctrl+C to stop.")
    try:
        make_server(state).run(sockets=[sock])
    finally:
        state.store.close()
