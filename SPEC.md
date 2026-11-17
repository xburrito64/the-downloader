# Spec: THE Downloader

A Spotify + YouTube downloader app. Version 2 of the spec, rewritten Nov 16, 2026 after a review of the first draft.

This file is the single source of truth for the project. It has two parts:

- **Sections 1ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“11** describe what is being built and why.
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
| API | Receives links, exposes queue, progress and settings to the UI | Starlette + uvicorn on 127.0.0.1 only, protected by a session token, server-sent events for live progress |
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
- At most 2ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“3 downloads run at once (adjustable in Settings).
- Only one download at a time reads a video's details, because that step starts Deno, which takes up to 300 MB for a second or two. The downloading itself still runs in parallel.
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

**When design work starts:** at milestone 6, not before. Milestones 1ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“5 have no visuals at all. Milestone 6 begins with a style concept (palette, fonts, one mocked-up screen, a motion sample) that I approve before any real screen is built. Collecting references and sketching ideas earlier is fine; building design earlier is not, because the screens depend on what the engine can actually report.

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
| requests | Direct calls to the Spotify Web API for my playlists, tracks and albums, and downloading cover art. spotipy is not used (decided at milestone 3). |
| mutagen | Tagging |
| Starlette + uvicorn | Local API server. FastAPI was planned and dropped at milestone 5 after measuring it (13 MB more memory, half a second more startup). |
| pywebview | The app window |

**Spotify setup (one time, done by me)**

- Create one app in the Spotify developer dashboard at https://developer.spotify.com/dashboard (requires my Premium account).
  - Redirect URI: exactly `http://127.0.0.1:43117/callback`
  - API used: Web API
- Copy the app's client ID. The client secret is not needed and should not be given to anyone.
- Log in once: `uv run thedownloader spotify-login --client-id MY_CLIENT_ID` (later from the Settings screen). The login token is stored in `%APPDATA%\THE Downloader\spotify.token`, never in the repo.

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
7. **UI v1 in its window**: Home, Queue, Library, Settings, in that order. Built to work, in the approved base style only: the palette, the two fonts, the cards and the basic motion from the concept. No extra art, no elaborate effects. **Design stays simple here on purpose.**
8. **Polish, and the real design pass**: this is where the design is worked out properly, together: mascot, stamp, empty-screen pictures, extra animation and detail. Also error messages, empty states and the efficiency measurements. **This is where we go hard on design.**
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
| 3 | Spotify provider | Done, Nov 16, 2026 |
| 4 | Core queue | Done, Nov 16, 2026 |
| 5 | API | Done, Nov 16, 2026 |
| 6 | Design concept | Direction approved Nov 16, 2026. Deep green `#063420` with the Foxglove pink accent |
| 7 | UI v1 in its window | Done, Nov 17, 2026. Tried by hand by me |
| 8 | Polish and the real design pass | Part 1 done (measurements, error messages, rough spots). Design pass, round 3 done (fullscreen fix, thick background trunks, rooted trees, three sign shapes). Waiting for my sign choice. Finished-download moment still open |
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
- An automated security review of the milestone 2 commit flagged that video titles were printed to the terminal unfiltered. A title containing terminal control codes could have moved the cursor or rewritten earlier output. All text from the internet now has control characters removed before it is printed, and file names have them removed too. Fixed in a follow-up commit.

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

### Nov 16, 2026: Milestone 3, Spotify provider

**Question from me**

- A YouTube video downloaded as an `.opus` file. That is intended: the terminal command downloads audio only unless `--video` is added. The UI will have a visible audio/video switch so this is not a surprise.
- The "'list' is not recognized" lines came from Windows, not the app: a link containing `&` must be put in quotes in the terminal. The download itself was correct.

**What was done**

- Read the current Spotify documentation (login flow, redirect rules, the playlist endpoint renamed in February 2026) and the documentation inside the installed ytmusicapi 1.12.3 before writing against them.
- Added dependencies: ytmusicapi, requests and mutagen (the last two were already installed as parts of yt-dlp and are now listed explicitly).
- Wrote `spotify_auth.py`: browser login, storing the login, and renewing it automatically.
- Wrote `providers/spotify.py`: reads track, album and playlist links and turns them into items; downloads by matching, downloading through the YouTube provider, then tagging.
- Wrote `matching.py`: searches YouTube Music and scores each candidate.
- Wrote `tagging.py`: writes title, artists, album, track number, year, recording code and cover art into `.opus`, `.m4a` and `.mp3` files.
- Added terminal commands: `spotify-login`, `spotify-logout` and `match`.

**Decisions made by Claude Code**

- **Direct calls to Spotify instead of the spotipy library.** Spotify renamed fields and endpoints in February 2026, and the app only needs four requests. Writing them directly avoids depending on a library keeping up.
- **Login without a client secret** (the "PKCE" method Spotify recommends for desktop apps). Only the client ID is stored in settings. The app asks for the smallest permissions that work: reading my private and collaborative playlists.
- **The login listens on the fixed local port 43117.** The first version used a free port chosen at that moment, which Spotify's documentation says is allowed for `127.0.0.1`. The first real login was refused with "redirect_uri: Not matching configuration", so the port is now fixed and registered with the app exactly. If the port is ever in use, the app says so instead of failing silently.
- **How a match is scored:** 45% title, 30% artist, 25% length. Bracketed notes, "- Remastered 2011" endings and "feat." parts are ignored when comparing titles.
- **Other versions are pushed down.** If one title says live, remix, karaoke, cover, acoustic, sped up and similar and the other does not, the score drops by 0.25.
- **A different artist is never chosen automatically.** A candidate with the right title and length but the wrong artist is a cover. It stays in the list for manual picking but is capped below the automatic threshold.
- **Minimum score 0.60.** Below that, the track is reported as "not found" rather than downloading something doubtful.
- **Official audio is preferred over music videos**, which often have intros and outros. Plain videos are only searched when the song catalogue has no convincing result.
- **Podcast episodes and local files in a playlist are skipped**, because there is nothing to match.
- **A missing cover is not an error.** The file is tagged without it.
- **Spotify downloads are always audio**, whatever the video setting says.
- **If Spotify says "slow down"**, the app waits when the wait is 15 seconds or less and otherwise reports how long to wait. It never retries in a loop, which is what gets apps blocked for 24 hours.

**What was tested**

| Test | Result |
| --- | --- |
| Recognising track, album and playlist links, including `intl-de` links and `spotify:` codes | Passed |
| Refusing artist links and short `spotify.link` addresses with a clear message | Passed |
| Login link contains every part Spotify requires | Passed |
| Turning Spotify's answers into items, with canned data: paging, the new and the old field name, skipped episodes and local files | Passed |
| "Not your playlist" and "not logged in" give clear messages (canned data) | Passed |
| Real YouTube Music search for four songs | Correct recording first in all four, score 1.00 |
| A made-up song | Reported as not found |
| Full path with made-up Spotify data: match, download, tag, as `.opus` and as `.mp3` | Passed; tags and cover read back correctly, files still play |

**Problems found and fixed**

- A live version and a karaoke version first scored 0.60 and 0.59, right at the threshold. The penalty for a different version was raised; they now score 0.50 and 0.49.
- A cover band scored 0.99 because the original artist's name appeared in its title. Catalogue songs are now compared on the artist field only.
- A musical-cast recording by "Killer Queen" tied with Queen at 1.00, because "Queen" is contained in that name. Artists are now compared as whole names.
- Cover art seemed not to embed in the first test. The cause was the test image link, which refused the request; tagging itself was correct.
- An automated security review flagged that the Spotify login file was written with default file permissions. On Windows the file sits in my user-profile folder, which other accounts on the PC cannot read anyway, so this was not exploitable here. The file and its folder are now created as owner-only regardless, which covers any other system. The login is still stored as a plain file, not in the Windows credential store; any program running under my own account could read it, as with most desktop apps.

**How to try it**

- `uv run thedownloader match "Queen" "Bohemian Rhapsody" --duration 354` shows the matches for a song. This works without Spotify.
- After the Spotify setup in section 8: `uv run thedownloader resolve "SPOTIFY_LINK"` and `uv run thedownloader download "SPOTIFY_LINK"`.

**Not done yet**

- **Nothing has been tested against the real Spotify service**: the login, reading a real track, album or playlist, and Spotify's real error answers. This needs my Spotify developer app. Until it is tested, the milestone is built but not confirmed.
- `.m4a` tagging is written but was not exercised, because YouTube Music delivered Opus for every test song.
- Artists whose names are written in different scripts on Spotify and YouTube Music (for example Japanese and romanised) may be reported as not found. They can be picked by hand in the preview later.
- **The GitHub repository still does not exist.** `gh auth login` is waiting for an answer in the terminal.

### Nov 16, 2026: Milestone 3 confirmed against real Spotify, GitHub repository created

This entry closes the open points of the entry above.

**What was done**

- After I logged in to GitHub again, the repository was created as **private** at https://github.com/xburrito64/the-downloader and all commits were pushed. From now on each milestone is pushed when it is done.
- I created the Spotify developer app and gave the client ID. It is saved in the settings file outside the repo. The client secret is not used.
- The first login attempt showed "redirect_uri: Not matching configuration". The redirect URI in my Spotify app had been entered wrongly. At the same time the app was changed to use one fixed address, `http://127.0.0.1:43117/callback`, so it is not known whether the earlier any-port approach would have worked with a correct entry. The fixed address is kept because it is the one that is confirmed to work.
- The second login succeeded.

**What was tested against the real service**

| Test | Result |
| --- | --- |
| Browser login and stored login | Passed |
| Read a real track | Passed in 0.5 s: title, artist, album, length, track number, year, recording code and cover all present |
| Read the album that track is on (12 tracks) | Passed in 0.1 s, track numbers in order |
| Read one of my own playlists (51 entries, so more than one page) | Passed in 0.4 s: 51 tracks, all with title, artist, recording code and cover |
| A playlist made by Spotify | Refused with a clear message |
| A track ID that does not exist | Clear message |
| Download and tag the real track | Passed in 11.5 s: 6.0 MB `.opus`, length 354 s, exactly what Spotify lists; all tags and the cover present |
| Startup check | Now reports Spotify as logged in |

The account has 154 playlists that I own; only one was read for the test. The test download was deleted afterwards.

**Problems found and fixed**

- Spotify answers "not found", not "forbidden", for playlists made by Spotify or by other people. The app showed "could not find this link", which was misleading. It now says that only playlists I own or collaborate on can be read.
- The embedded cover was stored without its width and height. Some players use these. The size is now read from the image (640 x 640 for Spotify covers) and stored.
- A single track was listed as "1 items" in the terminal. Fixed.

**Facts learned about Spotify's current behaviour**

- Tracks inside an album answer come without the recording code (ISRC). Tracks read on their own or from a playlist have it. Matching does not depend on it.
- Spotify covers are 640 x 640 JPEG files of about 100 KB.

**Not done yet**

- `.m4a` tagging is still not exercised, because YouTube Music delivered Opus for every test song.
- Reading a very large playlist (hundreds of tracks) was not tested. The largest tested had 51 entries.
- Matching was checked on a handful of well-known songs only. How often it picks a wrong version across a whole real playlist will show in milestone 4, when full playlists are downloaded.

### Nov 16, 2026: Milestone 4, core queue

**What was done**

- Wrote `store.py`: one SQLite table that holds both the queue and the history. A job starts as "queued" and ends as "done", "failed", "cancelled" or "skipped"; finished jobs are the history.
- Wrote `queue.py`: worker threads that take jobs from the store, with pause, resume, cancel, retry, duplicate skip and live events for the UI.
- Changed the `download` command to run through the queue, so downloads now run in parallel and are recorded.
- Added terminal commands: `resume`, `queue`, `history`, and `download --force`.

**Decisions made by Claude Code**

- **Threads, not a separate program per download.** yt-dlp and ffmpeg block while they work, so each download gets a worker thread. Idle workers sleep and use no CPU.
- **Queue and history are the same table.** Nothing is copied when a download finishes, and an interrupted download is never lost.
- **Progress is never written to disk.** It changes several times per second and only matters while the app is open.
- **Duplicates are recognised by source and ID plus audio or video.** The same video as audio and as video are two different downloads. A download is only skipped while its file still exists; a deleted file can be downloaded again. `--force` downloads again regardless.
- **Two different items with the same name both get saved.** The second gets its ID added to the file name, for example `Intro [abc123].opus`.
- **Pause keeps the partial file; cancel deletes it.** Both work on running and on waiting downloads.
- **Closing the app mid-download loses nothing.** Running downloads go back to the queue and continue from the partial file at the next start. The same happens after a crash.
- **One automatic second attempt.** A failed download is tried once more after 3 seconds before it is marked failed. An unexpected crash inside a download is not retried.
- **Every kind of failure ends as a status on that one job.** Nothing can escape and stop a worker.
- **Only one Deno at a time** (see "Efficiency measurements" below).

**What was tested**

With a simulated provider (no network, every path exercised), 35 checks, all passed:

| Area | Checked |
| --- | --- |
| Parallel work | Never more than the set number at once, and really in parallel |
| Failures | A failing and a crashing download are marked failed; the other 8 finish |
| Second attempt | A download that fails once succeeds on the automatic retry |
| Duplicates | Already downloaded, already in queue, same item twice in one list, deleted file, audio and video as separate, force |
| Same name | Two different items named "Intro" both saved |
| Pause and resume | Partial file kept; continues from it, not from zero |
| Cancel and retry | Partial file deleted; cancelled and failed jobs can be retried |
| Waiting jobs | Can be paused or cancelled before they start; a paused one does not start by itself |
| Closing and crash | Interrupted job returns to the queue and finishes after a restart, from its partial file |
| History | Newest first; search by title, artist and playlist name; `%` and `_` treated as plain text |
| Idle | 0.000 s of CPU in 6 s with 3 idle workers |

With real downloads through the queue (3 at a time):

| Test | Result |
| --- | --- |
| First 6 items of a YouTube playlist as audio | 6 of 6 done in 18.4 s |
| First 5 tracks of a Spotify album | 5 of 5 matched, downloaded and tagged in 23.6 s, all with cover |
| Adding the same album again | All 5 skipped as already downloaded |
| Terminal: download 2, then download 3 of the same playlist | Second run skipped 2 and downloaded 1 |
| Terminal: `history`, `history wing`, `queue`, `resume` | All correct |

All test downloads and the test history were deleted afterwards. The real history starts empty.

**Efficiency measurements (first measurement point)**

| What | Measured |
| --- | --- |
| Time until the queue is ready | 0.26 s |
| App memory, idle, before any link is read | 30 MB |
| App memory after yt-dlp is loaded | 67 MB |
| App memory, peak, 3 downloads at once | 121 MB |
| App memory, idle again afterwards | 79 MB |
| Helper programs, peak (they exist only while working) | 291 MB |
| Helper programs still running when idle | none |
| Progress updates sent | about 1.4 per second across all downloads |
| History database | 4 KB for 16 entries |
| CPU when idle | none measurable |

These numbers are for the engine only. The window and UI (milestone 7) will add their own memory, which is measured then.

**Problems found and fixed**

- **Helper memory peaked at 769 MB.** The cause was Deno, the JavaScript runtime yt-dlp needs for YouTube: up to 293 MB per copy, and three downloads started three copies at once. Now only one download at a time does the step that needs Deno. The peak dropped to 291 MB. The cost is speed on short files: six short downloads took 18.4 s instead of 13.2 s. For long files the difference is small, because the downloading itself still runs in parallel.
- **One real download failed in one of three test runs**, and the reason was not captured. It did not happen again. The automatic second attempt was added because of it. Whether that attempt would have saved that particular download is not known.

**Observations**

- A Spotify track was matched to a recording 5 seconds longer than Spotify's in one run (176 s instead of 171 s) and to the exact one in two other runs. YouTube Music does not always return the same search results. A 5-second difference is inside what the matching accepts. Every other track matched to the exact length.
- The app does not give memory back fully after yt-dlp has been loaded (79 MB idle afterwards, 30 MB before). That is yt-dlp staying loaded, which keeps the next download fast.

**How to try it**

- `uv run thedownloader download "LINK"` now downloads in parallel and records the result.
- Run the same command again to see already downloaded items being skipped.
- `uv run thedownloader history` lists finished downloads; `uv run thedownloader history "text"` searches them.
- Press Ctrl+C during a download, then `uv run thedownloader resume` to continue it.
- `uv run thedownloader queue` shows what is waiting or paused.

**Not done yet**

- Pause and cancel on single downloads work in the engine and are tested, but the terminal only offers "stop everything" (Ctrl+C) and `resume`. Per-item buttons come with the UI.
- Stopping with Ctrl+C in the terminal was not tested by hand; closing mid-download was tested through the code path it uses.
- A whole large playlist (hundreds of items) has still not been run. The largest real run was 6 items.
- The number of parallel downloads comes from the settings file (default 2). There is no command to change it yet; the Settings screen will do that.

### Nov 16, 2026: Milestone 5, API

**What was done**

- Wrote `api.py`: the local web interface the UI will talk to. It only translates between web requests and the engine; no download logic lives in it.
- Wrote `server.py`: starts and stops the server. The terminal uses it now and the app window will use it in milestone 7.
- Added the terminal command `serve`.

**What the API offers**

| Address | What it does |
| --- | --- |
| `GET /api/status` | The startup check, and whether Spotify is logged in |
| `GET` and `PUT /api/settings` | Read and change settings |
| `POST /api/spotify/login`, `/logout` | Start the browser login, or delete the stored login |
| `POST /api/resolve` | Read a link and return the preview, marking items that are already downloaded or queued |
| `GET /api/resolve/{id}/items/{n}/candidates` | The YouTube Music matches for one Spotify track |
| `POST /api/queue` | Queue all or some items of a preview, with format, quality and hand-picked matches |
| `GET /api/queue` | Everything waiting, running or paused |
| `POST /api/queue/pause-all`, `/resume-all` | Pause or continue everything |
| `POST /api/jobs/{id}/pause`, `/resume`, `/cancel`, `/retry`, `/reveal` | Act on one download; `reveal` shows the file in Explorer |
| `GET /api/history` | Finished downloads, newest first, with search and paging |
| `DELETE /api/history/{id}` | Remove an entry from the history; the file is not touched |
| `GET /api/events` | Live stream of progress and status changes |

**Decisions made by Claude Code**

- **Starlette instead of FastAPI.** The spec named FastAPI. It was built that way first, then measured: FastAPI cost 13 MB more memory and half a second more startup than Starlette, the smaller library it is built on, for the same handful of addresses. The API was rewritten on Starlette, with the checking of incoming values written by hand. Seven packages left the project.
- **The UI queues items by number, not by sending their details back.** The server keeps the last 20 previews in memory. This keeps requests tiny for large playlists, and means the server only ever downloads addresses it found itself.
- **Live updates use server-sent events**, a one-way stream from server to UI. It is simpler and lighter than a two-way connection, and the UI never has to ask "anything new?".
- **A UI that cannot keep up loses progress ticks, never status changes.**
- **Slow work runs in worker threads**, so reading a long playlist never freezes other requests or the live stream.
- **The last format and quality choice is saved** when something is queued.
- **Invalid settings are refused as a whole.** Nothing is changed unless every value passes.
- **Shutting down ends the live streams first.** Otherwise an open stream keeps the server waiting.

**Security decisions**

- The server listens on `127.0.0.1` only, so nothing outside this PC can reach it.
- Every request must carry a random token created at each start. Other programs and web pages on this PC do not know it.
- Requests that name any host other than `127.0.0.1` or `localhost` are refused. This blocks a known trick where a web page reaches a local server through a made-up domain name.
- The built-in documentation pages are switched off.
- "Show in Explorer" takes the file path from the history, never from the request.
- Chosen matches must look like a YouTube video ID; folder names in settings cannot point outside the output folder.

**What was tested**

Against a real server on a real port, with a simulated provider: 43 checks, all passed. The same 43 passed again after the rewrite on Starlette.

| Area | Checked |
| --- | --- |
| Access | No token, wrong token and a made-up host are refused; all 13 addresses need the token; docs pages are off |
| Settings | Read, change, saved to the file; seven kinds of invalid value refused; a refused change leaves everything as it was |
| Reading links | Preview, unknown link, provider error passed on as a message, empty link |
| Queue | Select items, repeated number counted once, pause, cancel, resume, retry, unknown item, four kinds of invalid request |
| Live events | Stream connects; progress and every status change arrive |
| Duplicates | Preview marks what is already downloaded; "add all" queues only the new ones |
| History | Newest first, search, paging, limits enforced, remove an entry without touching the file |
| Memory guard | An old preview is forgotten after 20 newer ones and says so |
| Large playlist | A 2000-item preview takes 0.05 s and is 271 KB |
| Shutdown | With a live stream open: stops in 0.2 s, and unfinished downloads return to the queue |

With the real providers behind the real server:

| Test | Result |
| --- | --- |
| Preview and download a YouTube video | Passed |
| Preview a Spotify track, list its 20 matches, download with a hand-picked match | Passed |
| Live events during those downloads | 11 progress and 6 status updates, covering downloading, converting and tagging |
| Preview of the same track afterwards | Marked as already downloaded |
| The `serve` command | Prints address and token, answers 1.2 s after launch, refuses requests without the token, stops cleanly |
| `serve` on a port another program holds | Clear message, no crash |

All test downloads were deleted afterwards.

**Efficiency measurements**

| What | With FastAPI | With Starlette (now) |
| --- | --- | --- |
| Loading the API | 45 MB, 0.76 s | 32 MB, 0.28 s |
| Server answering after start | 1.48 s | 0.97 s |
| Memory, idle, server and queue running | 67 MB | 54 MB |
| Memory, idle, after two downloads | 104 MB | 92 MB |
| CPU in 8 idle seconds, live stream open | 0.000 s | 0.016 s |

For comparison, the engine alone idles at about 22 to 30 MB; the web server adds roughly 10 MB and Starlette about 3 MB.

**Problems found and fixed**

- **The server could not shut down while the UI was connected.** An open live stream kept it waiting, so unfinished downloads were never put back in the queue. Shutdown now ends the streams first, and a 3-second limit covers the case where it is stopped from outside.
- One of my own tests assumed port 1 could not be used; on this PC it can. The test was wrong, not the app. The port-in-use message was then tested properly and reworded in plain language.

**How to try it**

- `uv run thedownloader serve` starts the API and prints its address and token. It is meant for the UI, so there is nothing to look at in a browser yet. Press Ctrl+C to stop it.

**Not done yet**

- **Cover thumbnails are not cached on disk yet.** The spec's efficiency rules call for it. For now the preview and queue hand out the original image addresses from Spotify and YouTube. The cache is built with the UI in milestone 7, where its effect can be measured.
- The Spotify login through the API was not run end to end. It uses the same login function that was tested for real in milestone 3; only the address that starts it is new.
- "Show in Explorer" was not run, because it opens a window on my desktop. Its refusal paths were not tested either.
- Changing the number of parallel downloads takes effect at the next start, not immediately.
- Stopping `serve` with Ctrl+C was not tested by hand; the 3-second limit that covers it comes from the web server's own setting.

### Nov 16, 2026: Milestone 6, design concept (waiting for approval)

**What was done**

- Built `design/concept.html`: one self-contained page (96 KB, fonts included) that shows the proposed look on a mocked-up Home screen. It can be opened by double-clicking it. Nothing in it downloads anything.
- Saved the two font files in `design/fonts/`.
- The page has switches for three palettes, for "reduce motion", and a "start over" button.

**The proposed concept**

- **Idea:** the app is a small enchanted program on an old machine. A link goes into a slot; what comes back is dealt onto the screen as cover-art cards, and each card is stamped when it has been downloaded.
- **Where the boldness goes:** the cards and their motion. Everything around them stays quiet.
- **Old-computer feel** comes from a pixel typeface, hard-edged shadows without blur, chunky keys that sink when pressed, and a still scanline overlay. It does not come from anything broken or glitchy.

**Colour: three palettes to choose from**

| Role | Plum | Lagoon | Daybreak (light) |
| --- | --- | --- | --- |
| Screen | `#2b1a3f` | `#0f3239` | `#ffe4cf` |
| Panels | `#38245a` | `#164550` | `#fff3e6` |
| Cards and keys | `#4a3175` | `#1e5b68` | `#ffffff` |
| Hard shadows | `#1a0f29` | `#08212a` | `#e3b89a` |
| Text | `#ffebd0` | `#fdf1d6` | `#3b2452` |
| The one accent | `#ffb52e` | `#ff9e6d` | `#7a4dff` |
| Done | `#74e8b8` | `#8be8a6` | `#1faf7a` |
| Problems | `#ff7fa8` | `#ff8fb1` | `#e8457a` |
| Focus and links | `#6ccbff` | `#7fd8e8` | `#2b8fd6` |

More than one palette can ship as selectable themes, because every colour is a named token.

**Type**

- **Jersey 15** for headings, buttons and numbers: a tall pixel face that stays readable when large.
- **Nunito** for everything that is read: titles, artists, settings, messages. Rounded and warm, so the pixels stay an accent.
- Both are bundled with the app, so no font is fetched from the internet at runtime.

**Motion rules**

- Things answer when touched: cards lean toward the pointer, buttons sink, the slot gulps a link.
- One arrival: cards are dealt in once when a link is read.
- A finished download gets stamped, with a short burst of sparks, once.
- Nothing moves on its own. No pulsing, floating or flicker while idle.
- "Reduce motion" turns all of it into instant changes, and the system setting for reduced motion switches it on automatically.
- Only position, rotation, scale and opacity are animated, which is the cheap kind for the graphics card.

**Where my own art can go**

- The small wisp in the title bar is a placeholder mascot.
- The "Got it" stamp, empty-screen pictures and the mascot are the natural spots for my drawings.
- The covers and song names in the mock-up are invented and drawn with gradients. No real cover art, and nothing taken from the games used as mood references.

**What was checked**

| Check | Result |
| --- | --- |
| Both fonts load | Yes |
| Layout at 1280 x 800 | Six cards in one row, window 592 px tall, no sideways scrolling |
| Text contrast, all three palettes | Every pairing at least 4.8 to 1 (4.5 is the usual minimum for small text) |
| Picking and unpicking cards, by mouse and by keyboard | Count and button label follow |
| Pretend download | Two at a time, progress blocks fill, picked cards get stamped, unpicked ones do not |
| Cards locked while downloading | Yes |
| Reduce motion | All changes become instant, cards sit straight |
| Palette switch | All colours and the swatch list follow |
| Idle | No animation running; the stylesheet contains no repeating animation |

**Problems found and fixed**

- The "Spotify playlist" chip had pale text on mint and was unreadable. A broader style rule was overriding the chip's own colour.
- Six cards were 22 px too wide for the row, so the sixth wrapped onto its own line.
- Daybreak failed contrast in two places (2.8 and 2.9) and Lagoon was just under in one (4.4). Colours were adjusted.
- The status bar said "0 saved" after a pretend download, and the spark pieces were never removed from the page.

**What was not checked**

- **I could not properly look at the finished page.** The app window was minimised or hidden for most of the work, which stops the page from being drawn, so only two screenshots succeeded. Layout, colours and behaviour were verified by measuring the page instead. How the motion actually feels can only be judged by me, by trying it.
- In one screenshot the digit 6 on the Download button looked close to an 8. A closer look failed for the reason above. If numbers in Jersey 15 are hard to tell apart, the number font should change.
- The narrow, phone-width layout was written but not measured. The app is a desktop window, so it matters little.
- The font licences were not verified. Both are believed to be under the SIL Open Font License; this is part of the licence check before any public release.

**Decisions waiting for me**

1. Which palette, or which ones as themes.
2. Drawn title bar, or the normal Windows one.
3. More or less tilt and bounce.
4. Whether I want to draw the mascot, the stamp and the empty-screen pictures myself.
5. Anything about the direction that feels wrong.

Milestone 7 (building the real screens) does not start until I have approved the concept.

### Nov 16, 2026: Milestone 6, my answers

**Decisions made by me**

1. **Palette:** I want to try a green one, with deep and rich greens. Plum, Lagoon and Daybreak are not chosen.
2. **Title bar:** the drawn one.
3. **Motion:** the tilt and bounce are good for now.
4. **My own art:** not now. The mascot, stamp and pictures are reworked together later.
5. **How hard to go on design, and when:** keep it simple now, and go hard later, once the design has been worked out and I feel confident about it.

**What was done**

- Added two green palettes to `design/concept.html`. It now opens in Forest.

| Role | Forest | Emerald |
| --- | --- | --- |
| Screen | `#0f2a1c` | `#06301f` |
| Panels | `#173b27` | `#0a402a` |
| Cards and keys | `#225338` | `#0f5738` |
| Hard shadows | `#06140d` | `#01150d` |
| Text | `#f7ecd0` | `#f4f0dc` |
| The one accent | `#ffc247` (gold) | `#ffa3bd` (pink) |
| Done | `#a6f29b` | `#ffe08a` |
| Problems | `#ff8fa3` | `#ff7a66` |
| Focus and links | `#7fd3f0` | `#86d9ff` |

- **Forest** is a warm, mossy green with a gold accent. **Emerald** is a cooler jewel green with a pink accent, and uses gold for "done" so that it stands apart from the green screen.
- Text contrast was calculated for both: the lowest pairing is 5.4 to 1 in Forest and 5.2 to 1 in Emerald.

**Decision made by Claude Code**

- **The build order now says in words where design effort goes.** Milestone 7 builds working screens in the base style only. Milestone 8 is the real design pass. This costs nothing later, because every colour, font, size and timing is a named token in one theme file, and the screens are built from a small set of shared parts. Restyling means changing the theme and those parts, not the screens.

**Not checked**

- The two greens were checked by calculation only. I have not seen them on screen; whether they look deep and rich enough is for me to judge.

**Still open**

- Forest, Emerald, or a different green.

### Nov 16, 2026: Milestone 6, a deeper green and four accent options

**Feedback from me**

- Forest is the better of the two greens, but the green should be more vibrant, richer and deeper.
- I do not like the yellow accent.
- **Where the design is heading:** a forest theme, with a background that is a forest of giant trees in pixel art. The main colours will be shades of green and brown.
- Question: which accent colours fit that? Maybe brown for now.

**What was done**

- Replaced the palette buttons in `design/concept.html` with four options that share one deeper, more saturated green and differ in accent and in whether cards are green or brown. The earlier Forest is kept as "Forest before" for comparison. The page opens in Redwood.

Shared by all four:

| Role | Colour |
| --- | --- |
| Screen | `#063420` |
| Panels | `#0a4a2c` |
| Hard shadows | `#020f08` |
| Text | `#f8efd8` |
| Done | `#a6f29b` |
| Focus and links | `#8fdcf0` |

The four options:

| Option | Accent | Cards and keys | Idea |
| --- | --- | --- | --- |
| Redwood | `#ff8552` rust orange | `#743c27` bark brown | The colour of redwood bark, brightened. Orange is the opposite of green, so it stands out most naturally |
| Foxglove | `#ff7fb6` pink | `#0f6239` green | Forest flowers and berries. The most fairy-tale of the four |
| Sunbeam | `#ffe6c4` warm cream | `#6a4630` wood brown | Light falling through the canopy. Calm, and nothing competes with the cover art |
| Bark | `#c07a4a` brown | `#0f6239` green | Brown as the accent, as asked, to see it for real |

**Advice from Claude Code on the accent question**

- **Brown works better as a material than as an accent.** In a forest of trunks, brown is the second-most common colour on screen, so a brown button has nothing to stand out against. The measurements agree: the Bark button stands out least of the four, at 4.0 to 1 against the screen and 2.2 to 1 against cards. Sunbeam's is 11.4 and 6.9; Redwood's is 5.7 and 3.6.
- **Brown is still part of the plan.** In Redwood and Sunbeam the cards and keys are brown, like wood, which leaves the accent free to be something that stands out.
- **Accents that suit a green and brown forest** are the things that stand out in a real one: bark-red and orange, the pinks and reds of flowers, berries and mushrooms, and pale warm light. Cool mist blue works as a quiet second colour and is already used for focus and links.
- This is advice, not a rule. The choice is a matter of taste and is mine.

**What was checked**

- Text contrast was calculated for all four: the lowest pairing is 5.5 to 1 in Redwood, 5.2 in Foxglove, 5.1 in Sunbeam and 5.2 in Bark.
- Brown cards were first almost exactly as bright as the green screen (1.2 to 1), so they separated by colour alone, which is weak for people with red-green colour blindness. The browns were lightened; cards are now 1.6 to 1.7 against the screen. The hard shadow under each card also separates them.

**Not checked**

- All of this was checked by calculation only. I (Claude Code) have not seen these colours on screen. Whether the green is now vibrant, rich and deep enough can only be judged by looking.
- How the colours sit against a pixel-art forest background is unknown, because that background does not exist yet. The accent may need another look once it does.

**Still open**

- Which accent option, or a different direction. (Answered in the next entry: Foxglove for now.)
- Whether cards and keys should be green or brown.

### Nov 16, 2026: Milestone 6, Foxglove chosen and the green taken from a reference image

**Decisions by me**

- **Accent: Foxglove (pink) for now.** With it come green cards and keys.
- **The green was still not right.** I sent a small reference image of the green I mean, and want the app's green to go a lot more in that direction.

**What the reference image showed**

Claude Code measured the image instead of guessing by eye.

| | Colour | Hue | Lightness |
| --- | --- | --- | --- |
| The reference image, main colour | `#18501c` | 124 (pure leaf green) | 20% |
| The green from the round before | `#063420` | 154 (leaning towards teal) | 11% |

So "more vibrant" meant two things: **less blue in the green, and nearly twice as light.** The earlier green was very saturated but so dark and so blue-leaning that it read as a dark teal. The image also has a pattern of slightly brighter dots (`#286030`), which may be worth using as a texture in milestone 8.

**What was done**

- The screen colour in `design/concept.html` is now exactly the reference green, and the other greens were rebuilt around it at the same hue. The page opens in Foxglove.
- The other three accent options (Redwood, Sunbeam, Bark) were moved onto the same green. "Green before" shows Foxglove on the darker green from the last round, for comparison. "Forest before" was removed.

| Role | Colour |
| --- | --- |
| Behind the window | `#0a260d` |
| Screen | `#18501c` |
| Panels | `#1f6424` |
| Cards and keys | `#236d29` |
| Hard shadows | `#071c09` |
| Text | `#f8efd8` |
| Quieter text | `#d9f0d6` |
| Accent | `#ff8fc0` |
| Done | `#b4f7a6` |
| Problem | `#ffc2b8` |
| Focus and links | `#a5e4f5` |

- Because the green is lighter, the pink, the quieter text and the "done", "problem" and "focus" colours were all lightened a little so text stays readable.

**What was checked**

- Text contrast in Foxglove, by calculation: lowest pairing is 4.2 to 1 (the "problem" colour on a card); ordinary text is 5.3 to 1 or better everywhere, 8.3 on the screen.
- The pink button against the screen is 4.5 to 1, against a card 3.0 to 1.

**The cost of a lighter green**

- Cards are now only 1.5 to 1 against the screen (they were 1.6 to 1.7). Making cards lighter would hurt the text on them, so the hard shadow under each card does more of the separating.
- In Redwood and Sunbeam the brown cards are 1.2 to 1.3 against the new green, so they separate mostly by colour. Not a problem while Foxglove is the choice, but it would need work if brown cards come back.

**Not checked**

- Still calculation only; Claude Code has not seen the colours on screen.

**Still open**

- Whether this green is right now. (Answered in the next entry: no, the earlier deep green stays.)

### Nov 16, 2026: Milestone 7, UI v1 (first half)

**Decision by me**

- The earlier deep green (`#063420`) was better after all. It stays, with the Foxglove pink accent. The lighter leaf green is kept in `design/concept.html` only as "Leaf green (tried)".

**What was built**

- `ui/`: the window's screens, written in Svelte and built with Vite into `ui/dist` (`npm install`, then `npm run build`, inside `ui`). Home, Queue, Library and Settings, in the base style only. All colours, fonts and timings are in `ui/src/theme.css`.
- Long lists only build the rows that are on screen (`VirtualGrid`).
- `covers.py`: the on-disk cover thumbnail cache. Each cover is fetched once, shrunk to 256 pixels by ffmpeg and reused. Only picture servers of Spotify and YouTube are ever contacted.
- The engine now also serves the UI files and the covers. A new setting, `reduce_motion`.
- `window.py` and the command `uv run thedownloader app`: the app in its own window (pywebview), with a drawn title bar. A window without a frame cannot be resized by its edges on Windows, so there is a grip in the bottom-right corner.

**Decisions by Claude Code**

- No image library was added for thumbnails; ffmpeg is installed anyway.
- The "reduce motion" switch is stored by the engine, because the window forgets everything between starts.
- Choosing a different YouTube match for a Spotify song is not in the UI yet.

**What was tested (in a browser tab against the real engine)**

- All four screens show up without errors.
- A real YouTube video was read, downloaded and went from Home through the Queue into the Library, with live updates.
- A playlist of 208 videos: only 30 cards exist on screen at a time, covers load.

### Nov 17, 2026: Milestone 7 finished

**The real window, tested by a script that looks inside it**

- Opens and shows the UI 1.5 to 3.5 seconds after launch. Both fonts load.
- The window functions answer: minimise, maximise, close, resize, folder picker are all reachable from the UI.
- The corner grip's resize works (1000 by 700 gave exactly that) and stops at the minimum size of 900 by 620.
- Closing the window stops the engine cleanly.
- The login token is removed from the window's address right after start.

**Problems found and fixed**

- **Maximise covered the taskbar.** That is what Windows does with a window that has no frame. The window is now moved and sized to the free area of its screen instead (2560 by 1392 on my screen, taskbar left visible).
- **A download that started very fast kept showing "Waiting".** The answer to "add to queue" arrived after the live update "now running" and overwrote it. The UI now trusts live updates for every change and never lets an answer replace newer news. The same fix was made for the Pause, Resume, Cancel and Try again buttons.
- **A resumed download showed its old speed** for a few seconds. It now shows "Starting" until new progress arrives.
- **Cards could stay invisible** if a link was read while the window was minimised. Fixed.

**Tested through the UI, against the real engine**

- Pause, resume and cancel on a running download; "Try again" on a failed one (a real failure: YouTube dropped the connection on a 3-hour video, and the second try worked).
- Something already downloaded is marked "Have it" and starts unpicked.
- Library search, including a search with no results.
- Settings: Save is only active after a change; a changed value is stored; a bad folder gives a clear message; the motion switch works.
- A Spotify track link is read and its cover is shown. Video is not offered for Spotify.
- The 35 queue checks and the 43 API checks still pass after the engine changes.

**Measurements (Nov 17, 2026, app open and idle on Home)**

| What | Value |
| --- | --- |
| Engine (Python) | 114 MB. It was 54 MB before the window library was added. |
| Window (WebView2, 6 processes) | 336 MB |
| Total | 456 MB |
| CPU while idle, everything together | 0.125 s in 20 s, about 0.6% of one core |
| UI files | 71 kB script, 13 kB styles, 56 kB fonts |
| Covers on disk | about 19 kB each |

- **The memory number is higher than I wanted.** Most of it is the window's browser engine, which every WebView2 app pays. The way it was counted also adds shared memory once per process, so the real cost is lower than 456 MB, but I have not measured by how much.
- Reducing it is a job for milestone 8: measure it properly, try WebView2's memory-saving options, and check what the window library adds to the engine.

**How to try it**

- With a terminal: `uv run thedownloader app`
- Without a terminal: double-click `.venv\Scripts\thedownloader-app.exe`
- After changing anything in `ui/src`: `npm run build` inside the `ui` folder.

**Not tested**

- **Nobody has used the real window by hand yet.** Dragging it by the title bar, dragging the corner grip with the mouse, the folder picker and "Show file" were not tried by a person. My script can press buttons inside the window but cannot drag with a mouse.
- Spotify login from the Settings screen (I am already logged in), and downloading a Spotify song through the UI. Both work from the terminal.
- A screen with a scaling other than 100%.
- Memory while downloading.

**Known rough spots, for milestone 8**

- A failed download shows yt-dlp's raw error text.
- With some items unpicked, the button only says "Pick all"; picking none takes two presses.
- YouTube covers are cut to a square.
- The first status check after a restart of the PC can take more than a second.
- Choosing a different YouTube match for a Spotify song is not in the UI.
- Changing "downloads at the same time" needs a restart.

### Nov 17, 2026: Milestone 8, part 1: measurements and rough spots

**Decision by me**

- I tried the window by hand: it works.

**Memory, measured properly**

The 456 MB from milestone 7 was misleading. It added up each process's memory including code that Windows shares between processes (and with Edge itself, if it is open). Counting only the memory that belongs to the app alone:

| Part | Memory of its own |
| --- | --- |
| Engine (Python, with the window library) | 55 MB |
| Window: main process | 28 MB |
| Window: graphics | 26 MB |
| Window: the page itself | 17 MB |
| Window: network, storage, crash reporter | 13 MB |
| **Total** | **about 141 MB** |

Window options that were tried:

| Option | Result | Decision |
| --- | --- | --- |
| Turn off graphics-card drawing | Saves 18 MB, but all motion would be drawn by the processor and be less smooth | Not used: smooth motion matters more here |
| Graphics inside the main process | Saves 9 MB, one process fewer, but a graphics crash would take the window down | Not used: too little gain |
| Switching off a list of Edge features | The window did not start at all | Not used |

So the window stays on its default options. 141 MB of its own is the cost of a window built on the browser engine Windows ships; a hand-made native window would be smaller but could not do this design.

**Rough spots fixed**

- **Failed downloads now say what happened in plain words** (new file `errors.py`). Example: instead of `[download] Got error: ('Connection aborted.', ConnectionResetError(10054, ...` it says "The connection dropped. Check your internet, then try again." Covered: connection problems, robot check, age-restricted, private, members-only, removed, not available in the country, not started yet, quality not offered, too many requests, refused, disk full, file in use, output folder unreachable, ffmpeg missing. Anything unknown is passed on, shortened.
- **"Downloads at the same time" now takes effect at once**, without a restart. Raising it starts more right away; lowering it lets the running ones finish first.
- **Pick all and Pick none are two buttons now.**

**What was tested**

- 16 new checks: 14 for the error wording, 2 for changing the number of parallel downloads while running (1 to 3, and 3 to 1). All pass.
- The 35 queue checks and 43 API checks still pass. One API check was updated, because it relied on the old behaviour that the parallel setting waited for a restart.
- The real window still opens and answers (script test).

**Not done**

- Choosing a different YouTube match for a Spotify song in the UI.
- YouTube covers are still cut to a square. This is a design question.
- Memory while downloading has not been measured with the window open.

**Next: the design pass, together.** Open questions for me are in the chat: the forest background, the mascot, the finished-download moment, empty screens, and cover shape.

### Nov 17, 2026: Milestone 8, design pass round 1: the forest

My answers to the design questions:

| Question | Answer |
| --- | --- |
| Where the forest shows | Behind the whole window |
| What kind of forest | Not real mammoth trees. Tall pines, with the colours and mood of a cartoon mystery-town forest |
| Who draws it | Claude |
| Mascot | Claude proposes a few |
| Finished-download moment | Decide later, once the forest look is settled |
| Empty screens | Pictures are fine, as long as it looks nice |
| YouTube covers | Wide cards |

**The forest background**

- The picture is drawn by a script, `design/make_forest.py`, and saved to `ui/src/art/forest.png`. It is original pixel art: three rows of pines from pale and far to dark and near, three big red-brown trunks in front, a ground with a dirt path, pink foxgloves, mushrooms and a few pale sparks. Changing the forest means changing numbers in the script and running it again.
- Why a script and not a painted file: every tree can be moved, recoloured or redrawn later without an art program, and the result is always the same.
- The picture is 640 by 400 pixels, 28 colours, 21 kB. It is shown at 3 screen pixels per art pixel, pinned to the bottom, and repeats seamlessly sideways, so it fits any window size without stretching. Above it, a tall window shows the picture's top colour.
- Cost: under 1 MB of memory, no animation, no processor use.
- The title bar, side rail and status bar are now slightly see-through (90% solid), so the forest runs faintly behind them.
- Behind a screen with content lies a green veil (80% solid) so text stays readable. On an empty screen the veil thins out toward the bottom, and the forest itself is the picture.
- Empty-screen messages now sit on a wooden sign with two posts. This brings brown into the interface.
- New theme values in `theme.css`: `--canopy`, `--panel-glass`, `--veil`, `--veil-thin`, `--wood`, `--wood-lit`, `--wood-dark`.

**Wide cards for videos**

- YouTube items are shown with a 16:9 picture: on Home (cards 216 wide instead of 140), and in the Queue and Library rows. Spotify items stay square.
- The engine makes a second small copy in that shape (384 by 216) when asked with `shape=wide`. Cutting to 16:9 also removes the black bars YouTube adds to its older 4:3 pictures.

**Mascot proposals**

- `design/mascots.png`, drawn by `design/make_mascots.py`: wisp (the current placeholder, enlarged), squirrel with an acorn, fox, mushroom, owl. Each is 16 by 16 pixels, shown large and at title-bar size. Nothing is chosen yet; the title bar still shows the small wisp.

**What was tested**

- Looked at in the window at 1120 by 760: Home empty, Home with a 182-video playlist (wide cards), Queue empty, Library empty, Settings. Text is readable everywhere.
- Wide covers on disk are 384 by 216, about 11 kB each.
- The 35 queue checks, 43 API checks and 16 milestone 8 checks all pass.

**Not done**

- Not looked at in the real app window yet, only in the browser view of the same page.
- The finished-download moment (waiting on purpose).
- The mascot (waiting for my choice).
- Still open from part 1: choosing a different match for a Spotify song, and memory while downloading.

### Nov 17, 2026: Milestone 8, design pass round 2: my first notes on the forest

What I said after seeing round 1: I really like the background as a first version, and the big trees in front look massive. Four things to change:

| Note | What was done |
| --- | --- |
| I like the mushroom mascot most | The mushroom is the mascot. It sits in the title bar at 32 pixels (`ui/src/art/mascot.png`, written by `design/make_mascots.py`) |
| The sign hangs in mid-air | The sign now stands low on the screen, and its posts reach down into the grass |
| The brown parts of the floor cut off harshly | The path was mostly hidden under the status bar, so only patches showed. It is now a winding band higher up, with soft dotted edges on both sides, unbroken across the window |
| The trees in the back are a bit thin | The far row is about half again as wide, the middle row about 40% wider with thicker trunks |

Also: the front ferns were moved up a little so the status bar no longer hides them.

**What was tested:** looked at in the browser view at 1120 by 760 (Home, empty). Only the picture and styles changed, the engine is untouched.

**Not done:** the finished-download moment; I have not said yet what else I would change in the forest.

### Nov 17, 2026: Milestone 8, design pass round 3: fullscreen, thick trunks, the sign

My notes after round 2, and what was done:

| Note | What was done |
| --- | --- |
| In fullscreen the trees just stop | Mistake in round 1: the picture was 1200 screen pixels tall, and a maximised window is taller. It is now 2160 tall (640 by 720 art pixels), enough for a 4K screen. The big trunks run to the very top and thin out into the dark there, so they never end in a straight cut |
| The background trees are still too thin, I want very thick trunks | Six thick trunks now stand far off, between the pale far pines and the middle pines, in a muted bark colour so they read as distant. The pines themselves also got thicker trunks (middle row 4 to 7 pixels, near row 6 to 10) |
| The bottom of the big trees looks pasted in | The trunk now sweeps out into roots in a curve, its bottom edge is scalloped into root toes, the foot is darker, it casts shade on the grass to the right, and grass grows up in front of it |
| The sign on the floor is a good idea but does not look good yet, try more | The sign is redrawn in the forest's own pixel style: hard edges in 3-pixel steps, planks, thick posts, tufts of grass at the foot. Three shapes are built, pictures in `design/signs/`: two posts (the default for now), one post, and a board lying on the ground |

- The three sign shapes live side by side in `ui/src/app.css` until one is chosen; the other two are then removed.
- The picture is now 35 kB and costs under 2 MB of memory.

**What was tested:** looked at in the browser view at 1120 by 760 and at 2560 by 1392 (maximised size). Trunks reach the top at both sizes. Only the picture and styles changed.

**Not done:** the sign choice is mine to make; the finished-download moment.
