"""Spotify login (Authorization Code with PKCE).

No client secret is involved. Logging in opens Spotify's own page in the
browser; Spotify then sends a one-time code back to a tiny local listener,
and the app swaps that code for tokens. Only the tokens are stored.
"""

import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from . import paths

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
# Must be registered in the Spotify dashboard exactly like this, port included.
# Spotify's docs say a port-less entry accepts any port, but in practice the login
# was refused with "redirect_uri: Not matching configuration", so the port is fixed.
REDIRECT_PORT = 43117
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
SCOPES = "playlist-read-private playlist-read-collaborative"
_LOGIN_TIMEOUT = 300  # seconds to finish the login in the browser
_EXPIRY_MARGIN = 60  # refresh a little before the token really expires


class SpotifyAuthError(Exception):
    """Login problem. The message is written for the user."""


def build_authorize_url(client_id: str, redirect_uri: str, state: str, verifier: str) -> str:
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return AUTHORIZE_URL + "?" + urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
            "scope": SCOPES,
        }
    )


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return
        self.server.result = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        ok = "code" in self.server.result
        text = "Login complete. You can close this tab." if ok else "Login was not completed. You can close this tab."
        body = f"<!doctype html><meta charset='utf-8'><title>THE Downloader</title><p style='font:16px sans-serif'>{text}</p>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:  # keep the terminal quiet
        pass


def _save_token(token: dict) -> None:
    file = paths.spotify_token_file()
    # Owner-only folder and file. On Windows the user-profile folder already keeps
    # other accounts out; the explicit modes cover any other system.
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = file.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(token))
    os.replace(tmp, file)


def _load_token() -> dict | None:
    try:
        token = json.loads(paths.spotify_token_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return token if isinstance(token, dict) and token.get("refresh_token") else None


def _request_token(data: dict) -> dict:
    import requests

    try:
        response = requests.post(TOKEN_URL, data=data, timeout=20)
    except requests.RequestException as exc:
        raise SpotifyAuthError(f"Could not reach Spotify: {exc}") from exc
    if response.status_code != 200:
        try:
            detail = response.json().get("error_description") or response.json().get("error")
        except ValueError:
            detail = response.text[:200]
        raise SpotifyAuthError(f"Spotify refused the login ({response.status_code}): {detail}")
    return response.json()


def _stored(token_response: dict, previous_refresh: str = "") -> dict:
    return {
        "access_token": token_response["access_token"],
        # Spotify may leave the refresh token out when refreshing; then the old one stays valid.
        "refresh_token": token_response.get("refresh_token") or previous_refresh,
        "expires_at": time.time() + int(token_response.get("expires_in", 3600)),
    }


def login(client_id: str, open_browser=webbrowser.open) -> None:
    """Run the browser login and store the tokens. Blocks until done or timed out."""
    if not client_id:
        raise SpotifyAuthError("No Spotify client ID is set.")
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(16)

    try:
        server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    except OSError as exc:
        raise SpotifyAuthError(
            f"Port {REDIRECT_PORT} is in use by another program, so the login cannot start. "
            "Close a second copy of this app if one is running, then try again."
        ) from exc
    server.result = None
    server.timeout = 1
    redirect_uri = REDIRECT_URI
    try:
        url = build_authorize_url(client_id, redirect_uri, state, verifier)
        if not open_browser(url):
            print(f"Open this link in your browser to log in:\n{url}")
        deadline = time.monotonic() + _LOGIN_TIMEOUT
        while server.result is None and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    result = server.result
    if result is None:
        raise SpotifyAuthError("The login was not finished in time. Please try again.")
    if result.get("state") != state:
        raise SpotifyAuthError("The login answer did not match this login attempt. Please try again.")
    if "code" not in result:
        raise SpotifyAuthError(f"Spotify login was cancelled or refused ({result.get('error', 'unknown reason')}).")

    token = _request_token(
        {
            "grant_type": "authorization_code",
            "code": result["code"],
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        }
    )
    _save_token(_stored(token))


def logout() -> None:
    paths.spotify_token_file().unlink(missing_ok=True)


def is_logged_in() -> bool:
    return _load_token() is not None


def access_token(client_id: str, force_refresh: bool = False) -> str:
    """A valid access token, refreshed when needed."""
    token = _load_token()
    if token is None:
        raise SpotifyAuthError("Not logged in to Spotify. Log in first.")
    if not force_refresh and token.get("access_token") and token.get("expires_at", 0) - _EXPIRY_MARGIN > time.time():
        return token["access_token"]
    try:
        refreshed = _request_token(
            {"grant_type": "refresh_token", "refresh_token": token["refresh_token"], "client_id": client_id}
        )
    except SpotifyAuthError as exc:
        if "invalid_grant" in str(exc) or "revoked" in str(exc).lower():
            raise SpotifyAuthError("The Spotify login has expired. Please log in again.") from exc
        raise
    stored = _stored(refreshed, previous_refresh=token["refresh_token"])
    _save_token(stored)
    return stored["access_token"]
