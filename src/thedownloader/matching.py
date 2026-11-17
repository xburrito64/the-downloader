"""Finds the YouTube Music recording that belongs to a Spotify track.

Spotify gives no audio, so every track is matched to a YouTube Music result.
Candidates are scored on title, artist and length; the best one is used unless
the user picks another in the preview.
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from .providers.base import Item

# Words that mark a different version of a song. A candidate that has one of
# these while the Spotify title does not (or the other way round) is penalised.
_VERSION_WORDS = (
    "live", "remix", "cover", "karaoke", "instrumental", "acoustic", "sped up", "slowed",
    "nightcore", "8d", "reverb", "demo", "edit", "extended", "remaster", "mix",
    "a cappella", "piano", "lofi", "music box", "orchestra", "8 bit",
    "bass boosted", "reaction", "tutorial", "backing track", "drumless", "off vocal",
)
# Other spellings and the Japanese words, each counted as the word it means: a karaoke
# track called カラオケ on Spotify and KARAOKE on YouTube Music is the same kind of version.
_SAME_AS = {
    "acapella": "a cappella", "アカペラ": "a cappella", "lo fi": "lofi", "カラオケ": "karaoke",
    "カバー": "cover", "歌ってみた": "cover", "弾いてみた": "cover",  # "sang it", "played it"
    "ピアノ": "piano", "オルゴール": "music box", "ライブ": "live",
}
# Written the way titles are compared (_normalise turns バ into ハ, so the words must match that).
_LOOK_FOR = [(word, word) for word in _VERSION_WORDS] + list(_SAME_AS.items())

# These mean the same recording, cut or mastered differently: a penalty, not a veto.
_SAME_RECORDING_WORDS = {"edit", "extended", "remaster", "mix"}
MIN_SCORE = 0.60  # below this, a candidate is not trusted as an automatic match
# A trusted match must also have nearly the same title and length. A wrong automatic pick is
# worse than none: the song then waits for a hand-picked recording instead.
TRUST_TITLE = 0.80
TRUST_SECONDS = 10
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


_LOOK_FOR = [(_normalise(word), meaning) for word, meaning in _LOOK_FOR]


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
    # Whole words for spaced languages; Japanese has no spaces between words.
    return {meaning for word, meaning in _LOOK_FOR if (f" {word} " if word.isascii() else word) in normalised}


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _title_score(wanted: str, title: str, artists: list[str], kind: str) -> float:
    """How alike the titles are.

    YouTube Music writes Japanese songs as "うっせぇわ - Usseewa" while Spotify may say only
    "Usseewa", so for catalogue songs each part counts. Videos are often called "Artist - Song":
    there the part after the artist counts.
    """
    best = _similarity(wanted, _core_title(title))
    first, _, rest = unicodedata.normalize("NFKC", title).partition(" - ")
    if rest and (kind == "song" or any(_similarity(_normalise(first), name) >= 0.85 for name in artists)):
        best = max(best, _similarity(wanted, _core_title(rest)))
    return best


def score(item: Item, title: str, artists: list[str], duration_seconds: int, kind: str) -> float:
    wanted_artists = [_normalise(name) for name in item.artist.split(", ") if name]
    title_score = _title_score(_core_title(item.title), title, wanted_artists, kind)

    found_names = [_normalise(name) for name in artists if name]
    video_title = f" {re.sub(r'\s+', ' ', _normalise(title))} "

    def artist_hit(name: str) -> float:
        # Whole names only: "Queen" must not match "Killer Queen".
        best = max((_similarity(name, found) for found in found_names), default=0.0)
        if best >= 0.85:
            return 1.0
        # For videos the artist is often only in the title ("Artist - Song"). That counts for
        # the fit, but not as the artist: anyone can upload "Ado - Usseewa (drums backing track)",
        # so such a video is never picked on its own. For catalogue songs only the artist field
        # counts, or a cover titled "... (by Queen)" would pass.
        if kind == "video" and f" {name} " in video_title:
            return max(best, 0.9)
        return best

    if wanted_artists:
        main_hit = artist_hit(wanted_artists[0])
        others = wanted_artists[1:]
        other_hit = sum(artist_hit(name) >= 1.0 for name in others) / len(others) if others else main_hit
        artist_score = 0.75 * main_hit + 0.25 * other_hit
    else:
        main_hit, artist_score = 0.5, 0.5

    if item.duration_seconds and duration_seconds:
        difference = abs(item.duration_seconds - duration_seconds)
        # Within 2 seconds is perfect; 30 seconds or more off is almost surely another version.
        duration_score = max(0.0, 1.0 - max(0, difference - 2) / 28)
    else:
        duration_score = 0.5

    total = 0.45 * title_score + 0.30 * artist_score + 0.25 * duration_score
    trusted = True
    different = _version_words(item.title) ^ _version_words(title)
    if different:
        total -= 0.25  # a live, karaoke or remix version must not pass as the original
    if different - _SAME_RECORDING_WORDS:
        trusted = False  # another performance altogether: only by hand
    if kind == "song":
        total += 0.03  # official audio is preferred over a music video with intro and outro
    if wanted_artists and main_hit < 1.0:
        # Right title and length but a different main artist is a cover, or another performance
        # ("Clair de Lune" by a flautist). A name that is merely close does not count either.
        # Keep it in the list for manual picking, but never let it be chosen automatically.
        trusted = False
    if title_score < TRUST_TITLE or (item.duration_seconds and duration_seconds
                                     and abs(item.duration_seconds - duration_seconds) > TRUST_SECONDS):
        # Another song that merely mentions the title (a soundtrack video named after the series),
        # or a different length. Shown for picking by hand, never chosen on its own.
        trusted = False
    total = max(0.0, min(1.0, total))
    # Untrusted results are scaled below MIN_SCORE instead of cut to one number, so their
    # order in Other match still says which is closest.
    return total if trusted else total * (MIN_SCORE - 0.01)


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


_LINK_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")
_BARE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_id_in(text: str) -> str:
    """The video ID in a pasted YouTube or YouTube Music link (or a bare ID), else ""."""
    text = text.strip()
    # An 11-letter word ("instrumental" is 12, "Bittersweet" is 11) is a search, not an ID.
    plain_word = text.isalpha() and (text.islower() or text.isupper() or text.istitle())
    if _BARE_ID.match(text) and not plain_word:
        return text
    found = _LINK_ID.search(text) if "youtu" in text else None
    return found.group(1) if found else ""


class _Found:
    """Candidates collected from several searches, each video once."""

    def __init__(self, item: Item) -> None:
        self.item = item
        self.by_id: dict[str, Candidate] = {}
        self.channels: dict[str, set[str]] = {}  # the artists' channel IDs, by video

    def add(self, results: list[dict], kind: str, album: str = "") -> None:
        for result in results:
            video_id = result.get("videoId")
            if not video_id or video_id in self.by_id:
                continue
            artists = [a.get("name", "") for a in result.get("artists") or [] if a]
            self.channels[video_id] = {a["id"] for a in result.get("artists") or [] if a and a.get("id")}
            title = result.get("title") or ""
            duration = _duration(result)
            self.by_id[video_id] = Candidate(
                video_id=video_id,
                title=title,
                artist=", ".join(a for a in artists if a),
                album=album or ((result.get("album") or {}).get("name", "") if isinstance(result.get("album"), dict) else ""),
                duration_seconds=duration,
                kind=kind,
                score=score(self.item, title, artists, duration, kind),
            )

    def best(self) -> float:
        return max((c.score for c in self.by_id.values()), default=0.0)

    def sorted(self) -> list[Candidate]:
        return sorted(self.by_id.values(), key=lambda c: c.score, reverse=True)


class Matcher:
    def __init__(self) -> None:
        self._ytm = None

    @property
    def _client(self):
        if self._ytm is None:
            from ytmusicapi import YTMusic  # loaded on first use

            self._ytm = YTMusic()
        return self._ytm

    def _search(self, query: str, kind: str, limit: int) -> list[dict]:
        return self._client.search(query, filter=kind, limit=limit) or []

    def candidates(self, item: Item, limit: int = 8) -> list[Candidate]:
        """Possible sources for a track, best first. Raises on network errors."""
        query = f"{item.artist.split(', ')[0]} {item.title}".strip()
        found = _Found(item)
        found.add(self._search(query, "songs", limit), "song")
        # The next steps only run when nothing convincing was found, so most songs cost one search.
        if found.best() < 0.85:
            self._from_album(item, found)
        if found.best() < 0.85:
            found.add(self._search(query, "videos", limit), "video")
            self._same_channel(item, found)
        return found.sorted()

    def search(self, item: Item, query: str, limit: int = 10) -> list[Candidate]:
        """The search typed into Other match: words, or a pasted YouTube / YouTube Music link.

        Results are scored against the Spotify song like the automatic ones, so the fit
        still tells how alike they are. Raises on network errors.
        """
        found = _Found(item)
        video_id = video_id_in(query)
        if video_id:
            song = self._client.get_song(video_id)
            details = song.get("videoDetails") or {}
            if (song.get("playabilityStatus") or {}).get("status") != "OK" or not details.get("videoId"):
                return []
            kind = "song" if details.get("musicVideoType") == "MUSIC_VIDEO_TYPE_ATV" else "video"
            found.add([{"videoId": details["videoId"], "title": details.get("title") or "",
                        "artists": [{"name": details.get("author") or ""}],
                        "duration_seconds": int(details.get("lengthSeconds") or 0)}], kind)
        elif query.strip():
            found.add(self._search(query.strip(), "songs", limit), "song")
            found.add(self._search(query.strip(), "videos", limit), "video")
        return found.sorted()

    def _from_album(self, item: Item, found: _Found) -> None:
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
        tracks = [t for t in album.get("tracks") or [] if t.get("isAvailable", True)]
        found.add(tracks, "song", album.get("title") or "")
        # In the right album, the same place and the same length is the same song, even when the
        # title is written another way (Spotify "Usseewa", YouTube Music "うっせぇわ").
        for track in tracks:
            candidate = found.by_id.get(track.get("videoId") or "")
            if (candidate and item.track_number and track.get("trackNumber") == item.track_number
                    and item.duration_seconds and abs(candidate.duration_seconds - item.duration_seconds) <= 3):
                names = [a.get("name", "") for a in track.get("artists") or [] if a]
                candidate.score = max(candidate.score, score(item, item.title, names, candidate.duration_seconds, "song"))

    def _same_channel(self, item: Item, found: _Found) -> None:
        """Count a result as the right artist when it comes from the artist's own channel.

        An artist can go by a different name on YouTube Music than on Spotify (Spotify says
        "Flicka Roe", YouTube Music lists the same songs under "Sofia Mills"). The name then
        looks like a cover by someone else. The channel behind the name is the same, so the
        artist's channel is looked up and results from it are scored with the Spotify name.
        Costs one extra search, and only when nothing convincing was found by name.
        """
        name = item.artist.split(", ")[0]
        if not name or found.best() >= MIN_SCORE:
            return
        wanted = _normalise(name)
        own = {
            result["browseId"]
            for result in self._search(name, "artists", 5)
            if result.get("browseId") and _similarity(_normalise(result.get("artist") or ""), wanted) >= 0.85
        }
        for video_id, candidate in found.by_id.items():
            if own & found.channels.get(video_id, set()):
                names = [name, *candidate.artist.split(", ")]
                candidate.score = score(item, candidate.title, names, candidate.duration_seconds, candidate.kind)
