"""Spotify provider: reads tracks, albums and my own playlists through the
official Web API, then gets the audio from the matching YouTube Music recording.

Spotify itself provides no audio. This module only reads names, numbers and
cover art from Spotify.
"""

import re
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .. import spotify_auth, tagging
from ..errors import VIDEO_BLOCKED
from ..matching import MIN_SCORE, Candidate, Matcher
from .base import DownloadOptions, Item, Progress, ProviderError, Resolved, Stopped
from .youtube import YouTubeProvider

_FALLBACKS = 3  # how many trusted recordings are tried when YouTube blocks the first ones

API = "https://api.spotify.com/v1"
_LINK = re.compile(
    r"(?:https?://open\.spotify\.com/(?:intl-[a-z]{2,3}/)?(track|album|playlist)/|spotify:(track|album|playlist):)"
    r"([A-Za-z0-9]{22})"
)
_MAX_WAIT = 15  # seconds the app is willing to wait when Spotify says "slow down"


def parse_link(link: str) -> tuple[str, str] | None:
    """("track" | "album" | "playlist", id) or None."""
    found = _LINK.search(link.strip())
    if not found:
        return None
    return (found.group(1) or found.group(2)), found.group(3)


def _largest_image(images: list | None) -> str:
    images = [i for i in (images or []) if i and i.get("url")]
    if not images:
        return ""
    return max(images, key=lambda i: i.get("width") or 0)["url"]


def _to_item(track: dict, album: dict | None = None) -> Item:
    album = album or track.get("album") or {}
    return Item(
        provider="spotify",
        source_id=track["id"],
        url=f"https://open.spotify.com/track/{track['id']}",
        title=track.get("name") or "",
        artist=", ".join(a["name"] for a in track.get("artists") or [] if a.get("name")),
        album=album.get("name") or "",
        duration_seconds=round((track.get("duration_ms") or 0) / 1000),
        cover_url=_largest_image(album.get("images")),
        track_number=track.get("track_number") or 0,
        year=(album.get("release_date") or "")[:4],
        isrc=(track.get("external_ids") or {}).get("isrc") or "",
    )


class SpotifyProvider:
    name = "spotify"

    def __init__(self, client_id: str, youtube: YouTubeProvider, matcher: Matcher | None = None) -> None:
        self._client_id = client_id
        self._youtube = youtube
        self._matcher = matcher or Matcher()
        self._session = None

    def handles(self, link: str) -> bool:
        link = link.strip()
        return link.startswith("spotify:") or "spotify.com/" in link or "spotify.link/" in link

    # ---- Spotify Web API -------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> dict:
        import requests

        if self._session is None:
            self._session = requests.Session()
        if not self._client_id:
            raise ProviderError("Spotify is not set up yet. Add your Spotify client ID and log in first.")

        refreshed = False
        waited = False
        while True:
            try:
                token = spotify_auth.access_token(self._client_id, force_refresh=refreshed)
            except spotify_auth.SpotifyAuthError as exc:
                raise ProviderError(str(exc)) from exc
            try:
                response = self._session.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=20)
            except requests.RequestException as exc:
                raise ProviderError(f"Could not reach Spotify: {exc}") from exc

            if response.status_code == 200:
                return response.json()
            if response.status_code == 401 and not refreshed:
                refreshed = True  # the token expired early; get a new one and try once more
                continue
            if response.status_code == 429:
                try:
                    wait = int(response.headers.get("Retry-After", "1"))
                except ValueError:
                    wait = 1
                if wait <= _MAX_WAIT and not waited:
                    waited = True
                    time.sleep(wait)
                    continue
                minutes = max(1, round(wait / 60))
                raise ProviderError(f"Spotify asked the app to slow down. Try again in about {minutes} minute(s).")
            if response.status_code == 401:
                raise ProviderError("The Spotify login is no longer valid. Please log in again.")
            if response.status_code == 403:
                raise _Forbidden()
            if response.status_code == 404:
                raise _NotFound()
            raise ProviderError(f"Spotify answered with an error ({response.status_code}).")

    def _pages(self, first_url: str, params: dict) -> list[dict]:
        entries: list[dict] = []
        page = self._get(first_url, params)
        while True:
            entries.extend(e for e in page.get("items") or [] if e)
            if not page.get("next"):
                return entries
            page = self._get(page["next"])  # "next" is a complete URL with its own parameters

    # ---- reading links ---------------------------------------------------

    def resolve(self, link: str) -> Resolved:
        parsed = parse_link(link)
        if parsed is None:
            if "spotify.link/" in link:
                raise ProviderError("Short spotify.link addresses are not supported. Use Share > Copy link in Spotify.")
            raise ProviderError("This Spotify link is not a track, album or playlist.")
        kind, spotify_id = parsed
        try:
            if kind == "track":
                return self._resolve_track(spotify_id)
            if kind == "album":
                return self._resolve_album(spotify_id)
            return self._resolve_playlist(spotify_id)
        except _Forbidden:
            if kind == "playlist":
                raise ProviderError(
                    "Spotify does not let the app read this playlist. Only playlists you own or collaborate on can be read."
                ) from None
            raise ProviderError("Spotify refused this request. Check that your Spotify Premium is active.") from None
        except _NotFound:
            if kind == "playlist":
                # Spotify answers "not found" for playlists made by Spotify or by other people.
                raise ProviderError(
                    "Spotify does not show this playlist to the app. Only playlists you own or collaborate on "
                    "can be read. If it is yours, check that the link is complete."
                ) from None
            raise ProviderError(f"Spotify could not find this {kind}. Check that the link is complete.") from None

    def _resolve_track(self, track_id: str) -> Resolved:
        item = _to_item(self._get(f"{API}/tracks/{track_id}"))
        return Resolved(kind="track", title=f"{item.artist} - {item.title}", items=[item], cover_url=item.cover_url)

    def _resolve_album(self, album_id: str) -> Resolved:
        album = self._get(f"{API}/albums/{album_id}")
        tracks = list((album.get("tracks") or {}).get("items") or [])
        next_url = (album.get("tracks") or {}).get("next")
        while next_url:
            page = self._get(next_url)
            tracks.extend(page.get("items") or [])
            next_url = page.get("next")
        items = [_to_item(t, album) for t in tracks if t and t.get("id")]
        artist = ", ".join(a["name"] for a in album.get("artists") or [] if a.get("name"))
        return Resolved(
            kind="album",
            title=f"{artist} - {album.get('name', '')}".strip(" -"),
            items=items,
            cover_url=_largest_image(album.get("images")),
        )

    def _resolve_playlist(self, playlist_id: str) -> Resolved:
        info = self._get(f"{API}/playlists/{playlist_id}", {"fields": "name,images"})
        entries = self._pages(f"{API}/playlists/{playlist_id}/items", {"limit": 50, "additional_types": "track"})
        items = []
        for entry in entries:
            # "item" is the current field name; "track" is the old one, kept as a fallback.
            track = entry.get("item") or entry.get("track")
            # Skip podcast episodes and local files, which have nothing to match.
            if not track or track.get("type") != "track" or track.get("is_local") or not track.get("id"):
                continue
            items.append(_to_item(track))
        return Resolved(
            kind="playlist",
            title=info.get("name") or "Playlist",
            items=items,
            cover_url=_largest_image(info.get("images")),
        )

    # ---- matching and downloading ----------------------------------------

    def candidates(self, item: Item) -> list[Candidate]:
        """Possible YouTube Music sources for a track, best first (for the preview)."""
        try:
            return self._matcher.candidates(item)
        except Exception as exc:  # ytmusicapi raises plain exceptions for network and parsing problems
            raise ProviderError(f"Searching YouTube Music failed: {exc}") from exc

    def download(
        self,
        item: Item,
        options: DownloadOptions,
        on_progress: Callable[[Progress], None],
        should_stop: Callable[[], bool],
    ) -> Path:
        if item.match_id:
            choices = [item.match_id]  # picked by hand: only that one
        else:
            found = self.candidates(item)
            if not found or found[0].score < MIN_SCORE:
                raise ProviderError("No matching recording was found on YouTube Music.")
            # The best few that are trusted. If YouTube blocks one (age-restricted, removed,
            # not in this country), the same song is often there again as another recording.
            choices = [c.video_id for c in found if c.score >= MIN_SCORE][:_FALLBACKS]

        path = None
        for number, video_id in enumerate(choices):
            if should_stop():
                raise Stopped()
            source = Item(
                provider="youtube",
                source_id=video_id,
                url=f"https://music.youtube.com/watch?v={video_id}",
                title=item.title,
            )
            try:
                # Spotify downloads are always audio.
                path = self._youtube.download(source, replace(options, mode="audio"), on_progress, should_stop)
                break
            except ProviderError as exc:
                if str(exc) not in VIDEO_BLOCKED or number == len(choices) - 1:
                    raise
                on_progress(Progress(0.0, 0.0, "waiting"))  # the next recording starts from the beginning

        on_progress(Progress(1.0, 0.0, "tagging"))
        try:
            tagging.tag(path, item, tagging.fetch_cover(item.cover_url))
        except tagging.TaggingError as exc:
            # The audio is fine; a tagging problem should not throw the download away.
            raise ProviderError(f"Downloaded, but tagging failed: {exc}") from exc
        return path


class _Forbidden(Exception):
    """Spotify answered 403; the caller knows which message fits."""


class _NotFound(Exception):
    """Spotify answered 404; the caller knows which message fits."""
