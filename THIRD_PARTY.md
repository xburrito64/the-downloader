# Third-party software

THE Downloader is MIT licensed (see `LICENSE`). It is built on the work below. None of it is copied into this repository except the two fonts; everything else is installed by `uv` and `npm` from its own source.

## Python packages (installed with `uv sync`)

| Package | Used for | Licence |
| --- | --- | --- |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) and yt-dlp-ejs | Downloading from YouTube and YouTube Music | Unlicense (yt-dlp-ejs: Unlicense, MIT and ISC) |
| [ytmusicapi](https://github.com/sigma67/ytmusicapi) | Searching YouTube Music for a Spotify song | MIT |
| [mutagen](https://github.com/quodlibet/mutagen) | Writing title, artist, album and cover into audio files | GPL-2.0-or-later |
| [pywebview](https://github.com/r0x0r/pywebview) | The app window | BSD-3-Clause |
| [Starlette](https://github.com/encode/starlette) and [Uvicorn](https://github.com/encode/uvicorn) | The local connection between window and engine | BSD-3-Clause |
| [Requests](https://github.com/psf/requests) | Talking to the Spotify Web API | Apache-2.0 |

Their own dependencies (pythonnet, bottle, anyio, certifi and others) carry MIT, BSD, Apache, MPL-2.0 or PSF licences.

**About mutagen:** it is GPL-licensed. This repository only contains source code that imports it, and MIT is compatible with the GPL. Anyone who builds and hands out a packaged program that includes mutagen has to follow the GPL for that package.

## UI build tools (installed with `npm install`)

| Package | Licence |
| --- | --- |
| [Svelte](https://github.com/sveltejs/svelte) | MIT |
| [Vite](https://github.com/vitejs/vite) and @sveltejs/vite-plugin-svelte | MIT |

## Fonts (included in `ui/src/fonts/`)

| Font | Copyright | Licence |
| --- | --- | --- |
| Jersey 15 | 2023 The Soft Type Project Authors | SIL Open Font License 1.1 |
| Nunito | 2014 The Nunito Project Authors | SIL Open Font License 1.1 |

The full licence text and copyright lines are in `ui/src/fonts/OFL.txt`.

## Programs you install yourself

These are never included in the repository.

| Program | Used for | Licence |
| --- | --- | --- |
| [ffmpeg](https://ffmpeg.org) | Converting audio, joining video and sound, shrinking covers | LGPL or GPL, depending on the build |
| [Deno](https://deno.com) | Lets yt-dlp solve YouTube's JavaScript checks | MIT |

## Art

The forest background, the mushroom mascot and the other pixel art are original, drawn by the scripts in `design/`, and fall under this project's MIT licence.

The README screenshots show a thumbnail from "Big Buck Bunny" (Blender Foundation, CC BY 3.0, peach.blender.org) and from "Me at the zoo", the first video uploaded to YouTube.
