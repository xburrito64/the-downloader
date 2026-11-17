"""Finds the YouTube Music recording that belongs to a Spotify track.

Spotify gives no audio, so every track is matched to a YouTube Music result.
Candidates are scored on title, artist and length; the best one is used unless
the user picks another in the preview.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher

from .providers.base import Item

# Words that mark a different version of a song. A candidate that has one of
# these while the Spotify title does not (or the other way round) is penalised.
_VERSION_WORDS = (
    "live", "remix", "cover", "karaoke", "instrumental", "acoustic", "sped up", "slowed",
    "nightcore", "8d", "reverb", "demo", "edit", "extended", "remaster", "mix",
)
MIN_SCORE = 0.60  # below this, a candidate is not trusted as an automatic match
_BRACKETS = re.compile(r"[\(\[【][^\)\]】]*[\)\]】]")
_FEAT = re.compile(r"\b(feat\.?|ft\.?|featuring|with)\b.*", re.IGNORECASE)


@dataclass
class Candidate:
    video_id: str
    title: str
    artist: str
    album: str
    duration_seconds: int
    kind: str  # "song" (official audio) or "video"
    score: float  # 0.0 to 1.0


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE).strip()


def _core_title(title: str) -> str:
    """Title without bracketed notes, "- Remastered 2011" tails and featured artists."""
    # Japanese and Chinese titles use full-width brackets and dashes: （より） becomes (より) first.
    title = unicodedata.normalize("NFKC", title)
    title = _BRACKETS.sub(" ", title)
    title = title.split(" - ")[0]
    title = _FEAT.sub("", title)
    return re.sub(r"\s+", " ", _normalise(title)).strip()


def _version_words(title: str) -> set[str]:
    normalised = f" {re.sub(r'\s+', ' ', _normalise(title))} "
    return {word for word in _VERSION_WORDS if f" {word} " in normalised}


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score(item: Item, title: str, artists: list[str], duration_seconds: int, kind: str) -> float:
    wanted_title = _core_title(item.title)
    found_title = _core_title(title)
    title_score = _similarity(wanted_title, found_title)

    wanted_artists = [_normalise(name) for name in item.artist.split(", ") if name]
    found_names = [_normalise(name) for name in artists if name]
    video_title = f" {re.sub(r'\s+', ' ', _normalise(title))} "

    def artist_hit(name: str) -> float:
        # Whole names only: "Queen" must not match "Killer Queen".
        best = max((_similarity(name, found) for found in found_names), default=0.0)
        if best >= 0.85:
            return 1.0
        # For videos the artist is often only in the title ("Artist - Song"). For catalogue
        # songs only the artist field counts, or a cover titled "... (by Queen)" would pass.
        if kind == "video" and f" {name} " in video_title:
            return 1.0
        return best

    if wanted_artists:
        main_hit = artist_hit(wanted_artists[0])
        others = wanted_artists[1:]
        other_hit = sum(artist_hit(name) >= 1.0 for name in others) / len(others) if others else main_hit
        artist_score = 0.75 * main_hit + 0.25 * other_hit
    else:
        artist_score = 0.5

    if item.duration_seconds and duration_seconds:
        difference = abs(item.duration_seconds - duration_seconds)
        # Within 2 seconds is perfect; 30 seconds or more off is almost surely another version.
        duration_score = max(0.0, 1.0 - max(0, difference - 2) / 28)
    else:
        duration_score = 0.5

    total = 0.45 * title_score + 0.30 * artist_score + 0.25 * duration_score
    if _version_words(item.title) != _version_words(title):
        total -= 0.25  # a live, karaoke or remix version must not pass as the original
    if kind == "song":
        total += 0.03  # official audio is preferred over a music video with intro and outro
    if wanted_artists and artist_score < 0.5:
        # Right title and length but a different artist is a cover. Keep it in the list
        # for manual picking, but never let it be chosen automatically.
        total = min(total, MIN_SCORE - 0.05)
    return max(0.0, min(1.0, total))


def _duration(result: dict) -> int:
    if result.get("duration_seconds"):
        return int(result["duration_seconds"])
    parts = str(result.get("duration") or "").split(":")
    try:
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return seconds
    except ValueError:
        return 0


class Matcher:
    def __init__(self) -> None:
        self._client = None

    def _search(self, query: str, kind: str, limit: int) -> list[dict]:
        if self._client is None:
            from ytmusicapi import YTMusic  # loaded on first use

            self._client = YTMusic()
        return self._client.search(query, filter=kind, limit=limit) or []

    def candidates(self, item: Item, limit: int = 8) -> list[Candidate]:
        """Possible sources for a track, best first. Raises on network errors."""
        query = f"{item.artist.split(', ')[0]} {item.title}".strip()
        found: dict[str, Candidate] = {}
        channels: dict[str, set[str]] = {}  # the artists' channel IDs, by video

        def collect(results: list[dict], kind: str, album: str = "") -> None:
            for result in results:
                video_id = result.get("videoId")
                if not video_id or video_id in found:
                    continue
                artists = [a.get("name", "") for a in result.get("artists") or [] if a]
                channels[video_id] = {a["id"] for a in result.get("artists") or [] if a and a.get("id")}
                title = result.get("title") or ""
                duration = _duration(result)
                found[video_id] = Candidate(
                    video_id=video_id,
                    title=title,
                    artist=", ".join(a for a in artists if a),
                    album=album or ((result.get("album") or {}).get("name", "") if isinstance(result.get("album"), dict) else ""),
                    duration_seconds=duration,
                    kind=kind,
                    score=score(item, title, artists, duration, kind),
                )

        def best() -> float:
            return max((c.score for c in found.values()), default=0.0)

        collect(self._search(query, "songs", limit), "song")
        # The next steps only run when nothing convincing was found, so most songs cost one search.
        if best() < 0.85:
            self._from_album(item, collect)
        if best() < 0.85:
            collect(self._search(query, "videos", limit), "video")
            self._same_channel(item, found, channels)
        return sorted(found.values(), key=lambda c: c.score, reverse=True)

    def _from_album(self, item: Item, collect: Callable[..., None]) -> None:
        """Look for the song inside its album on YouTube Music.

        A search by title fails when the title is a common word or the name of the whole
        series: the soundtrack song "無職転生" drowns among the other 29 tracks of the
        "無職転生" soundtrack, which all mention the series. The album itself is easy to
        find, and its track list holds the song. Costs two requests.
        """
        if not item.album or not item.artist:
            return
        wanted = _core_title(item.album)
        try:
            albums = self._search(f"{item.album} {item.artist.split(', ')[0]}", "albums", 5)
            match = next((a for a in albums[:5] if a.get("browseId")
                          and _similarity(_core_title(a.get("title") or ""), wanted) >= 0.85), None)
            if match is None:
                return
            album = self._client.get_album(match["browseId"])
        except Exception:
            return  # an extra step; the title search and the video search still count
        collect([t for t in album.get("tracks") or [] if t.get("isAvailable", True)], "song", album.get("title") or "")

    def _same_channel(self, item: Item, found: dict[str, Candidate], channels: dict[str, set[str]]) -> None:
        """Count a result as the right artist when it comes from the artist's own channel.

        An artist can go by a different name on YouTube Music than on Spotify (Spotify says
        "Flicka Roe", YouTube Music lists the same songs under "Sofia Mills"). The name then
        looks like a cover by someone else. The channel behind the name is the same, so the
        artist's channel is looked up and results from it are scored with the Spotify name.
        Costs one extra search, and only when nothing convincing was found by name.
        """
        name = item.artist.split(", ")[0]
        if not name or max((c.score for c in found.values()), default=0.0) >= MIN_SCORE:
            return
        wanted = _normalise(name)
        own = {
            result["browseId"]
            for result in self._search(name, "artists", 5)
            if result.get("browseId") and _similarity(_normalise(result.get("artist") or ""), wanted) >= 0.85
        }
        for video_id, candidate in found.items():
            if own & channels.get(video_id, set()):
                names = [name, *candidate.artist.split(", ")]
                candidate.score = score(item, candidate.title, names, candidate.duration_seconds, candidate.kind)
