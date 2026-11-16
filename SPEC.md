# Spec: THE Downloader

A Spotify + YouTube downloader app. Version 2 of the spec, rewritten Nov 16, 2026 after a review of the first draft.

This file is the single source of truth for the project. It has two parts:

- **Sections 1–11** describe what is being built and why.
- **Section 12 (Development log)** records every step of development as it happens. It is updated at the end of each milestone, and whenever a decision changes.

## 1. Goal

One personal desktop app that downloads music from **Spotify links** (my own playlists, plus tracks and albums) and media from **YouTube links** (videos, playlists), in a single clean and good-looking interface. It runs locally on my Windows PC, in its own window. It is for my own use. If it turns out clean, I may put it on GitHub under MIT, but the app comes first and publishing is optional.

**Top priority besides working correctly: efficiency.** Low memory use, low CPU use, and a UI that always feels smooth.

## 2. Key decisions (and why)

| Decision | Why |
| --- | --- |
| **Engine in Python** | yt-dlp is Python and is the only tool that keeps up with YouTube's changes. Any other language would still have to launch it underneath. The heavy work (network, ffmpeg conversion) does not run in Python anyway, so a rewrite in a "faster" language would save little and add fragility. |
| **No spotDL** | It is a large dependency that brings its own web server and many extras, and since Spotify's 2026 API changes it runs in a reduced mode with frequent rate-limit blocks. A small Spotify module of my own is lighter and more reliable. This replaces the first draft's plan. |
| **Spotify through the official API, with my own login** | Since February 2026, Spotify developer apps require Premium on the owner's account (I have it), and the API only returns the tracks of playlists I own or collaborate on. That matches my use: my own playlists. |
| **Matching through YouTube Music search** | Spotify provides no audio. Each Spotify track is matched to a YouTube Music result and downloaded with yt-dlp. |
| **No re-encoding by default** | YouTube audio is already Opus or AAC. Keeping it as-is is near-instant and loses no quality. Converting (for example to mp3) costs CPU and lowers quality, so it is optional. |
| **Own window from the start** | The UI is a web front end shown in a native window through pywebview, which uses the WebView2 component already built into Windows 11. No bundled browser. |
| **UI separate from the engine** | The engine knows nothing about screens. The look can be redesigned without touching download logic. |
| **Front end in Svelte** | It compiles to a very small bundle with no heavy runtime, which suits the efficiency goal, and its component structure makes restyling easy. |
| **Use libraries, don't copy code** | yt-dlp and the other libraries are imported as dependencies. YoutubeDownloader is used only as feature inspiration (quality picker, queue, progress display). |
| **Update-friendly** | yt-dlp stays a normal dependency that updates in one command, and the app shows its version. |
| **Project lives in `C:\Dev`, not OneDrive** | The dependencies are tens of thousands of small files. OneDrive syncing them causes slowdowns and file-lock errors. |

## 3. Architecture

| Layer | Job | Tech |
| --- | --- | --- |
| Window | Native window that displays the UI | pywebview (WebView2) |
| UI | Screens, link box, queue view, library view, settings | Svelte, built with Vite into static files |
| API | Receives links, exposes queue, progress and settings to the UI | FastAPI + uvicorn on localhost only, server-sent events for live progress |
| Core | Detects link type, builds jobs, runs them in a worker queue, handles retries | Plain Python modules |
| Providers | One module per source, same interface: `resolve(link)` then `download(item)` | `spotify` (official Web API + YouTube Music matching), `youtube` (yt-dlp) |
| Tagging | Writes title, artist, album, cover art and track number into files | mutagen |
| Storage | Queue, history, settings | SQLite, plus one config file kept outside the repo |

The provider interface is the important part. Adding a third source later (for example SoundCloud through yt-dlp) should mean one new module and no change to the UI.

### How a Spotify download works

1. I log in to Spotify once from the Settings screen. The app keeps the login token locally.
2. The app reads the track list (title, artists, album, duration, cover, track number, and ISRC code when Spotify provides it).
3. For each track it searches YouTube Music and scores the candidates by title, artist and duration.
4. The preview shows the chosen match. If it looks wrong (live version, remix), I can pick another candidate.
5. yt-dlp downloads the audio, then mutagen writes the Spotify metadata and cover art into the file.

## 4. Efficiency rules

These apply to every milestone.

- Downloads stream straight to disk. Nothing large is held in memory.
- At most 2–3 downloads run at once (adjustable in Settings).
- Audio is kept in its original format unless I ask for a conversion.
- yt-dlp and other heavy libraries are loaded only when first needed, so the app starts fast.
- Progress updates are sent to the UI a few times per second at most, not on every chunk.
- Long lists (big playlists, history) only render the rows that are visible.
- Cover art is cached on disk as small thumbnails. Full-size covers are only fetched for tagging.
- No background polling. When nothing is downloading, the app does nothing.
- Memory and startup time are measured at the end of milestones 4, 7 and 8 and written into the development log.

## 5. Features

**v1 (must have)**

- Paste one or more links into one box. The app detects the type: Spotify track, album or playlist, or YouTube video or playlist.
- Preview before downloading: title, artist, cover, duration, and number of tracks for playlists.
- For Spotify tracks, show the matched YouTube source and let me pick a different one.
- Choose format and quality. Audio: original (Opus or m4a, no conversion, the default), or converted to mp3. Video: best, 1080p, 720p. Remember my last choice.
- Download queue with live progress per item, plus pause, cancel and retry. Pause means stop and later resume from the partial file.
- Tag Spotify downloads with proper metadata and cover art.
- Choose the output folder and the naming template. Defaults: everything goes into `Downloads\THE Downloader`, with a `YouTube` folder (files named `{title}`) and a `Spotify` folder (files named `{artist} - {title}`). Templates can add subfolders, for example `{artist}/{album}/{track} - {title}`.
- History: what was downloaded, when, and where it was saved. Skip items that were already downloaded (recognised by Spotify track ID or YouTube video ID).
- Clear error messages when a track can't be found or a download fails. The rest of the queue keeps going.
- Startup check for ffmpeg, Deno and the Spotify login, with plain instructions when something is missing.

**Known limits of v1**

- Spotify playlists made by other people or by Spotify itself can't be read. Spotify's API no longer returns their tracks. The app says so clearly instead of failing silently.
- No FLAC. YouTube has no lossless audio, so a FLAC file would only be a bigger copy of the same quality.

**v2 (later, if wanted)**

- Reading public Spotify playlists from other people (would need a separate method that reads Spotify's public pages and can break).
- Downloading my Spotify "Liked Songs".
- Sync a Spotify playlist: re-check it and only download new tracks.
- Lyrics embedding.
- Built-in player for downloaded files.
- Theme options and a more customised look.
- A button to update yt-dlp from inside the app.

## 6. Screens

1. **Home / Download**: big link box, detected-type chip, preview card(s), format and quality picker, Download button.
2. **Queue**: active and waiting items with cover, progress bar, speed, and pause/cancel/retry buttons.
3. **Library / History**: grid or list of finished downloads with cover art, search, and an "open folder" button.
4. **Settings**: output folder, naming template, default format and quality, parallel downloads, Spotify login, ffmpeg and Deno check, yt-dlp version.

## 7. Look and feel

**Concept (decided Nov 16, 2026):** a slightly magical old computer program, but colourful and modern. Warm and playful, and it feels like a game.

- **Mood references:** the "program inside an old computer" feeling of Pony Island and Buddy Simulator 1984, without any horror and with nothing broken on purpose. These are references for mood only; the app gets its own original art and no assets or designs are taken from those games.
- **Motion:** juicy, game-like motion in the spirit of Balatro: things bounce, tilt, settle and react when touched.
- **Still true from before:** cover art is a main visual, and progress is shown with smooth animation.

Rules that keep this compatible with the efficiency goal:

- Animations only move and fade elements (the cheap kind for the graphics card), and stop completely when nothing is happening.
- Retro screen effects (scanlines, glow, grain) are static overlays, not constantly running animations.
- A "reduce motion" switch in Settings turns the game-like motion down.
- All colours, fonts, spacing and motion timings live in one theme file so the look is easy to change.

**When design work starts:** at milestone 6, not before. Milestones 1–5 have no visuals at all. Milestone 6 begins with a style concept (palette, fonts, one mocked-up screen, a motion sample) that I approve before any real screen is built. Collecting references and sketching ideas earlier is fine; building design earlier is not, because the screens depend on what the engine can actually report.

## 8. Requirements and dependencies

**Programs on my PC**

| Item | Purpose | Status on Nov 16, 2026 |
| --- | --- | --- |
| Python 3.13 | Runtime for the engine | Installed |
| uv | Creates the Python environment and installs dependencies | Installed |
| Node.js | Only needed to build the UI, not to run the app | Installed (v24) |
| git | Version history | Installed |
| ffmpeg | Merging video and audio, conversion | **Missing, must be installed** |
| Deno | JavaScript runtime that yt-dlp now needs for YouTube | **Missing, must be installed** |

ffmpeg and Deno are never bundled with the project.

**Python libraries**

| Library | Purpose |
| --- | --- |
| yt-dlp + yt-dlp-ejs | Downloading from YouTube. Kept updatable, never copied into the project. |
| ytmusicapi | Searching YouTube Music to match Spotify tracks |
| spotipy, or direct calls to the Spotify Web API | Reading my Spotify playlists, tracks and albums. Decided at milestone 3 after reading the current docs. |
| mutagen | Tagging |
| FastAPI + uvicorn | Local API server |
| pywebview | The app window |

**Spotify setup (one time, done by me)**

- Create one app in the Spotify developer dashboard (requires my Premium account) and copy its client ID into Settings.
- Log in once from the app. The token is stored in the local config file, never in the repo.

## 9. Licensing and repo rules (only matters if I publish)

- My own code: MIT license.
- Add a `THIRD_PARTY.md` crediting every library used and the inspiration from YoutubeDownloader, with each project's license name and link.
- Before the first public release, check the license of every dependency in the lockfile.
- Don't include ffmpeg or Deno binaries, API keys, login tokens, or downloaded media in the repo.
- The README states that the tool is for personal use and that downloading may conflict with YouTube's and Spotify's terms of service.

## 10. Open questions for me to decide

None at the moment.

Decided on Nov 16, 2026: language and architecture, Spotify method, own window, project location, app name (THE Downloader), look concept (section 7), output folder layout (section 5).

## 11. Build order

Each milestone is checked before the next one starts, and each one ends with an entry in the development log.

1. **Skeleton**: project structure, Python environment, dependency list, config loading, startup check for ffmpeg, Deno and Spotify login.
2. **YouTube provider**: resolve a link, list playlist items, download audio or video with the chosen quality. Tested in the terminal, with no UI.
3. **Spotify provider**: login, read track, album and own-playlist links, match to YouTube Music, download, tag with cover art. Tested in the terminal.
4. **Core queue**: worker queue with progress events, pause, retry, cancel, SQLite history, duplicate skip.
5. **API**: endpoints and live progress for the UI.
6. **Design concept**: palette, fonts, one mocked-up screen and a motion sample, approved by me before any real screen is built. **This is where design work starts.**
7. **UI v1 in its window**: Home, Queue, Library, Settings, in that order, built in the approved style.
8. **Polish**: error messages, empty states, extra animation and art details, efficiency measurements.
9. **Repo hygiene** (only if publishing): README, `THIRD_PARTY.md`, license, screenshots.

### Working rules for Claude Code

- Read the current docs and source of yt-dlp, ytmusicapi and the Spotify Web API before writing code against them. They change often, so don't rely on memory.
- Do not copy code out of spotDL or YoutubeDownloader.
- Keep providers behind one shared interface, and keep the UI free of download logic.
- One failing track must never stop a whole playlist or queue.
- Explain each major decision briefly, so I can follow why it was done that way.
- After each milestone: tell me what works and how to try it, and add the log entry below.

## 12. Development log

Newest entry at the bottom. Each entry records: date, what was done, decisions made and why, what was tested and the result, how to try it, and anything left open.

### Milestone status

| # | Milestone | Status |
| --- | --- | --- |
| 0 | Spec review and planning | Done, Nov 16, 2026 |
| 1 | Skeleton | Done, Nov 16, 2026 |
| 2 | YouTube provider | Done, Nov 16, 2026 |
| 3 | Spotify provider | Not started |
| 4 | Core queue | Not started |
| 5 | API | Not started |
| 6 | Design concept | Not started |
| 7 | UI v1 in its window | Not started |
| 8 | Polish | Not started |
| 9 | Repo hygiene | Not started (optional) |

### Nov 16, 2026: Milestone 0, spec review and planning

**What was done**

- Reviewed the first draft of the spec against the current state of Spotify, yt-dlp and spotDL.
- Rewrote the spec as this version 2.
- Created the project folder at `C:\Dev\Youtube-Spotify-Downloader`. The original folder inside OneDrive was empty.
- Checked which required programs are installed (table in section 8).

**What the review found**

- Spotify changed its developer rules in February 2026: Premium is required, and playlist tracks are only returned for playlists the logged-in user owns or collaborates on. The first draft's "free client ID and secret" plan no longer works as written.
- spotDL now defaults to a reduced keyless mode, and users report 24-hour rate-limit blocks.
- yt-dlp needs an external JavaScript runtime (Deno recommended) and the `yt-dlp-ejs` package for YouTube since November 2025. The first draft only checked for ffmpeg.
- FLAC output would not be real lossless audio.
- yt-dlp has no true pause. It is implemented as stop and resume.
- Spotify-to-YouTube matching can pick the wrong version, so the preview needs a way to choose another match.

**Decisions made by me**

- I have Spotify Premium, and I mostly download my own playlists, so the official API is the Spotify method.
- The app opens in its own window from the start.
- The project moves out of OneDrive into `C:\Dev`.

**Decisions made by Claude Code**

- Python stays as the engine language; spotDL is dropped; Svelte for the UI; pywebview for the window; original audio format as the default. Reasons are in section 2.

**Not done yet**

- Nothing has been built. No code exists.
- ffmpeg and Deno are not installed.
- The three questions in section 10 are open.

**Sources checked**

- Spotify February 2026 migration guide: https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide
- Spotify July 2026 quota update: https://developer.spotify.com/blog/2026-07-23-web-api-quota-updates
- yt-dlp JavaScript runtime announcement: https://github.com/yt-dlp/yt-dlp/issues/15012
- spotDL v4.5.0 release notes: https://newreleases.io/project/github/spotDL/spotify-downloader/release/v4.5.0

### Nov 16, 2026: Milestone 1, skeleton

**Decisions made by me**

- App name: THE Downloader.
- Look concept: a slightly magical old computer program, colourful, modern, warm and game-like (section 7).
- Output: one downloads folder with a `YouTube` and a `Spotify` folder inside, files directly in them.

**What was done**

- Installed ffmpeg 9.0.2 and Deno 2.9.8 with winget.
- Created the Python project with uv (Python 3.13) and a git repository. Nothing is committed yet.
- Added the first dependency: yt-dlp 2026.10.26, which brings yt-dlp-ejs 0.8.0 with it. Other libraries are added in the milestone that first uses them, so each one is checked against its current docs at that point.
- Wrote the skeleton in `src/thedownloader/`:
  - `paths.py`: where settings, the Spotify token and the history database live (all outside the repo).
  - `config.py`: settings with built-in defaults, loaded from and saved to one JSON file.
  - `startup.py`: the startup check for ffmpeg, Deno, yt-dlp and Spotify.
  - `providers/base.py`: the shared interface both sources will implement (`resolve` and `download`).
  - `cli.py`: terminal commands used to test milestones before the UI exists.
- Added a design-concept milestone (now milestone 6) before the UI build, so the style is agreed before screens are built.

**Decisions made by Claude Code**

- **Settings are a JSON file in `%APPDATA%\THE Downloader`**, not in the project folder. The Settings screen will write it, so it needs no hand editing, and it can never end up in the repo.
- **Unknown or wrongly typed settings are ignored** and replaced by defaults, so an old settings file keeps working after updates.
- **The startup check reads the PATH stored in Windows**, not only the one the app was started with. Otherwise a tool installed while the app is open would be reported as missing until a restart.
- **Spotify is reported as "not set" rather than "missing"**, because YouTube downloads work without it.

**What was tested**

- `thedownloader check` reports ffmpeg, Deno and yt-dlp as OK and Spotify as not set. Passed.
- Settings: partial file, wrong value type, unknown key, save and reload. Passed.
- A settings file saved with a hidden byte-order marker (as Notepad and PowerShell do) failed to load at first. Fixed, then passed.
- A broken settings file gives a clear error message. Passed.

**How to try it**

In a terminal in the project folder:

- `uv run thedownloader check` shows the startup check.
- `uv run thedownloader init-config` creates the settings file with default values.

**Not done yet**

- No downloading exists. That starts with milestone 2.
- The Spotify app and login are set up in milestone 3.
- An old, dead PATH entry on this PC points to an old ffmpeg 7.1.1 folder in the user folder, a folder that no longer exists. It is harmless and was left alone.

### Nov 16, 2026: Milestone 2, YouTube provider

**What was done**

- Committed milestone 1 to the local git repository.
- Read the option documentation inside the installed yt-dlp 2026.10.26 before writing against it.
- Wrote `providers/youtube.py`:
  - `resolve` reads a video or playlist link and returns title, channel, duration, thumbnail and video ID for each item, without downloading.
  - `download` downloads one item as audio or video, reports progress, and can be stopped.
- Wrote `naming.py`, which turns a naming template and an item into a file path that is safe on Windows.
- Added two terminal commands: `resolve` and `download`.
- Added two error types to the shared provider interface: one for "this failed, here is why" and one for "stopped on request".

**Decisions made by Claude Code**

- **Audio "original" copies the audio stream out unchanged.** The result is usually an `.opus` file at about 128 kbps, which is the best YouTube offers. Nothing is re-encoded.
- **mp3 is converted at 192 kbps.** Higher would only make bigger files, because the source is about 128 kbps.
- **Video "best" takes the highest quality whatever the file type** (often `.mkv`). **"1080p" and "720p" prefer streams that fit a normal `.mp4`**, which plays everywhere. In both cases picture and sound are joined by copying, never re-encoded.
- **A video link that contains a playlist ID downloads only that video.** Only a real playlist link downloads the whole playlist. This avoids accidentally queuing 200 videos.
- **Channel pages and search pages are refused** with a clear message. yt-dlp would treat them as playlists with hundreds or thousands of videos.
- **Playlists are listed in one request** instead of one request per video, so a preview appears quickly. Deleted and private videos are left out of the list.
- **Progress is sent at most four times per second**, and for video (two files: picture and sound) it is calculated over both together, so the bar runs once from 0 to 100.
- **Stopping keeps the partial file**, and the next download of the same item continues from there. This is the basis for pause in milestone 4.
- **yt-dlp is loaded only when a link is first read**, so `thedownloader check` and the later app start do not pay for it.

**What was tested**

| Test | Result |
| --- | --- |
| Read a single video link | Passed |
| Read a playlist link (17 to 19 items, three different playlists) | Passed |
| Video link with a playlist ID in it gives the single video | Passed |
| Removed video, unsupported site, search page, channel page | Each gives a clear one-line error |
| Audio original (19-second video) | Passed, `.opus` |
| Audio mp3 | Passed, `.mp3` |
| Video 720p (10-minute video, 97.5 MB) | Passed, `.mp4` |
| Stop at 29%, then download again | Partial file kept; resumed from 29% and finished |
| Download an already finished file again | Skipped in 2.5 s, file not repeated |
| First 2 items of a playlist as audio | Both downloaded, Opus at about 127 kbps |
| File names with forbidden characters, `..`, reserved names such as `CON` | All made safe |

All test downloads were deleted afterwards.

**Problems found and fixed**

- Search-page links were first accepted and returned 433 "items" after 16 seconds. They are now refused.
- 720p video first came out as `.mkv`. It now prefers `.mp4`-compatible streams.
- The standard yt-dlp test video no longer exists on YouTube. That was the video, not the app; other videos work.

**How to try it**

In a terminal in the project folder (replace LINK with a YouTube link in quotes):

- `uv run thedownloader resolve LINK` shows what the link contains.
- `uv run thedownloader download LINK` downloads audio in original quality.
- `uv run thedownloader download LINK --audio-format mp3` downloads mp3.
- `uv run thedownloader download LINK --video --quality 1080p` downloads video.
- `uv run thedownloader download LINK --limit 3` downloads only the first 3 items of a playlist.

Files land in `Downloads\THE Downloader\YouTube`.

**Not done yet**

- **The GitHub repository does not exist yet.** The GitHub login on this PC has expired. After `gh auth login` is run once, the repository can be created and both commits pushed.
- Downloads run one after another in the terminal. Parallel downloads, the queue, history and duplicate skip come in milestone 4.
- yt-dlp prints a harmless line "Unknown codec iamf.001.001.Opus" in the terminal for some videos. It comes from yt-dlp itself and will not be visible in the app window.
- Age-restricted and members-only videos were not tested. They need a logged-in YouTube account, which the spec does not include.
