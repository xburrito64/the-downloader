"""Turns technical error text into a sentence that says what happened and what to do.

yt-dlp and Windows report problems in their own words. This file is the one place
that translates them. Anything it does not recognise is passed through, shortened.
"""

import re

# (pattern, message). The first pattern that matches wins, so specific ones come first.
_KNOWN: list[tuple[re.Pattern, str]] = [(re.compile(pattern, re.IGNORECASE), message) for pattern, message in [
    (r"confirm you.?re not a bot",
     "YouTube is asking for a robot check right now. Wait a few minutes, then try again."),
    (r"confirm your age|age.restricted|inappropriate for some users",
     "This video is age-restricted. YouTube only hands it out to a logged-in account, which this app does not use."),
    (r"private video", "This video is private."),
    (r"members.only|join this channel", "This video is for channel members only."),
    (r"available in your country|geo.?restrict|blocked it in your country|not available from your location",
     "This video is not available in your country."),
    (r"premieres in|live event will begin|is not yet available|offline\.$",
     "This video has not started yet. Try again once it is out."),
    (r"copyright (claim|grounds)|terminated|has been removed|video unavailable|no longer available|does not exist",
     "This video is no longer available on YouTube."),
    (r"requested format is not available",
     "YouTube does not offer this video in the chosen quality. Pick Best and try again."),
    (r"HTTP Error 429|too many requests",
     "YouTube is slowing this PC down for asking too often. Wait a few minutes, then try again."),
    (r"HTTP Error 403|forbidden",
     "YouTube refused the download. This usually passes; if it keeps happening, yt-dlp needs an update."),
    (r"no space left|Errno 28|not enough space|disk.*full", "The disk is full. Free some space, then try again."),
    (r"permission denied|WinError 5\b|WinError 32\b|being used by another process|access is denied",
     "The file could not be written. It may be open in another program, or the folder is protected."),
    (r"WinError 3\b|cannot find the path|No such file or directory",
     "The output folder could not be reached. Check it in Settings."),
    (r"ffmpeg.*not (found|installed)|ffprobe.*not found",
     "ffmpeg is missing. Open Settings to see how to install it."),
    (r"connection (aborted|reset|refused)|forcibly closed|timed out|timeout|getaddrinfo|name resolution|"
     r"network is unreachable|WinError 100\d\d|incompleteread|connection broken|remote end closed|ssl",
     "The connection dropped. Check your internet, then try again."),
    (r"no match|could not find a match", "No matching song was found on YouTube Music."),
]]

_MAX_LENGTH = 200


def explain(raw: str) -> str:
    text = " ".join(str(raw).split())
    for pattern, message in _KNOWN:
        if pattern.search(text):
            return message
    text = re.sub(r"^\[[\w:+ ]+\]\s*", "", text)  # "[download] " and similar labels
    text = re.sub(r"^Got error:\s*", "", text)
    if len(text) > _MAX_LENGTH:
        text = text[: _MAX_LENGTH - 1].rstrip() + "…"
    return text or "Unknown error"
