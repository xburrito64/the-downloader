"""Terminal entry point. Used to test each milestone before the UI exists."""

import argparse
import re
import sys

from . import APP_NAME, config, paths, startup


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _clean(text: object) -> str:
    """Remove control characters from text that came from the internet.

    A video title could otherwise carry terminal escape codes that move the
    cursor, recolour the screen or rewrite what was printed before.
    """
    return _CONTROL_CHARS.sub("", str(text))


def cmd_check(_args: argparse.Namespace) -> int:
    try:
        settings = config.load()
    except config.ConfigError as exc:
        print(f"[ERROR]   {exc}")
        return 1

    print(f"{APP_NAME} startup check\n")
    all_required_ok = True
    for check in startup.run_checks(settings):
        if check.ok:
            status = "[OK]"
        elif check.required:
            status = "[MISSING]"
            all_required_ok = False
        else:
            status = "[NOT SET]"
        print(f"{status:<10}{check.name}: {check.detail}")
        if not check.ok:
            print(f"{'':<10}-> {check.fix}")

    print(f"\nSettings file:  {paths.config_file()}")
    print(f"Downloads go to: {settings.output_path('youtube')}")
    print(f"                 {settings.output_path('spotify')}")
    return 0 if all_required_ok else 1


def cmd_init_config(_args: argparse.Namespace) -> int:
    file = paths.config_file()
    if file.exists():
        print(f"Settings file already exists: {file}")
        return 0
    config.save(config.Settings())
    print(f"Created settings file with defaults: {file}")
    return 0


def _providers(settings: config.Settings) -> list:
    from .providers.spotify import SpotifyProvider
    from .providers.youtube import YouTubeProvider

    youtube = YouTubeProvider(
        ffmpeg_path=startup.find_program("ffmpeg", settings.ffmpeg_path),
        deno_path=startup.find_program("deno", settings.deno_path),
    )
    return [SpotifyProvider(settings.spotify_client_id, youtube), youtube]


def _resolve(link: str, settings: config.Settings):
    """Find the provider for a link and read what the link contains."""
    from .providers.base import ProviderError

    for provider in _providers(settings):
        if provider.handles(link):
            return provider, provider.resolve(link)
    raise ProviderError("This link is not recognised. Supported: YouTube videos and playlists, Spotify tracks, albums and playlists.")


def _duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def cmd_resolve(args: argparse.Namespace) -> int:
    from .providers.base import ProviderError

    try:
        _provider, resolved = _resolve(args.link, config.load())
    except (ProviderError, config.ConfigError) as exc:
        print(f"[ERROR] {_clean(exc)}")
        return 1

    print(f"{resolved.kind.capitalize()}: {_clean(resolved.title)}")
    if resolved.kind in ("playlist", "album"):
        print(f"{len(resolved.items)} items")
    for number, item in enumerate(resolved.items[: args.show], start=1):
        length = _duration(item.duration_seconds) if item.duration_seconds else "?"
        print(f"{number:>4}. {_clean(item.title)}  |  {_clean(item.artist)}  |  {length}  |  {_clean(item.source_id)}")
    if len(resolved.items) > args.show:
        print(f"      ... and {len(resolved.items) - args.show} more")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    from . import naming
    from .providers.base import DownloadOptions, ProviderError, Stopped

    try:
        settings = config.load()
        provider, resolved = _resolve(args.link, settings)
    except (ProviderError, config.ConfigError) as exc:
        print(f"[ERROR] {_clean(exc)}")
        return 1

    items = resolved.items[: args.limit] if args.limit else resolved.items
    folder = settings.output_path(provider.name)
    template = settings.spotify_template if provider.name == "spotify" else settings.youtube_template
    print(f"{resolved.kind.capitalize()}: {_clean(resolved.title)}  ({len(items)} to download)")
    print(f"Saving to: {folder}\n")

    failed = 0
    for number, item in enumerate(items, start=1):
        label = f"[{number}/{len(items)}] {_clean(item.title)}"
        options = DownloadOptions(
            mode="video" if args.video else "audio",
            audio_format=args.audio_format,
            video_quality=args.quality,
            target=folder / naming.render(template, item),
        )

        def show(progress, label=label) -> None:
            if progress.stage == "downloading":
                speed = f"{progress.speed_bytes_per_second / 1_048_576:.1f} MB/s"
                print(f"\r{label}  {progress.fraction:>4.0%}  {speed}      ", end="", flush=True)
            else:
                print(f"\r{label}  {progress.stage}...            ", end="", flush=True)

        # One failing item must never stop the rest.
        try:
            path = provider.download(item, options, show, lambda: False)
        except ProviderError as exc:
            failed += 1
            print(f"\r{label}  FAILED: {_clean(exc)}")
        except Stopped:
            print(f"\r{label}  stopped")
            break
        except KeyboardInterrupt:
            print(f"\r{label}  stopped. The partial file is kept and will be resumed next time.")
            return 1
        else:
            print(f"\r{label}  done -> {_clean(path.name)}            ")

    print(f"\nFinished: {len(items) - failed} ok, {failed} failed.")
    return 1 if failed else 0


def cmd_spotify_login(args: argparse.Namespace) -> int:
    from . import spotify_auth

    try:
        settings = config.load()
    except config.ConfigError as exc:
        print(f"[ERROR] {_clean(exc)}")
        return 1
    if args.client_id:
        settings.spotify_client_id = args.client_id.strip()
        config.save(settings)
    if not settings.spotify_client_id:
        print("[ERROR] No Spotify client ID is saved yet. Run: thedownloader spotify-login --client-id YOUR_CLIENT_ID")
        return 1

    print("Opening Spotify in your browser. Log in and press Agree, then come back here.")
    print(f"If Spotify shows 'redirect_uri: Not matching configuration', add this exact redirect URI")
    print(f"to your app in the Spotify developer dashboard: {spotify_auth.REDIRECT_URI}")
    try:
        spotify_auth.login(settings.spotify_client_id)
    except spotify_auth.SpotifyAuthError as exc:
        print(f"[ERROR] {_clean(exc)}")
        return 1
    print("Logged in to Spotify.")
    return 0


def cmd_spotify_logout(_args: argparse.Namespace) -> int:
    from . import spotify_auth

    spotify_auth.logout()
    print("Logged out of Spotify. The stored login was deleted.")
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    """Show which YouTube Music recordings would be used for a song (no Spotify login needed)."""
    from .matching import MIN_SCORE, Matcher
    from .providers.base import Item

    item = Item("spotify", "", "", args.title, artist=args.artist, duration_seconds=args.duration)
    try:
        found = Matcher().candidates(item)
    except Exception as exc:
        print(f"[ERROR] Searching YouTube Music failed: {_clean(exc)}")
        return 1
    if not found:
        print("No results.")
        return 1
    for number, c in enumerate(found[: args.show], start=1):
        mark = "*" if number == 1 and c.score >= MIN_SCORE else " "
        print(
            f"{mark}{number:>2}. {c.score:.2f}  {_clean(c.title)}  |  {_clean(c.artist)}  |  "
            f"{_duration(c.duration_seconds)}  |  {c.kind}  |  {_clean(c.video_id)}"
        )
    if found[0].score < MIN_SCORE:
        print(f"\nNo candidate reaches the minimum score of {MIN_SCORE:.2f}; this track would be reported as not found.")
    return 0


def main() -> None:
    # Titles can contain characters the Windows terminal cannot show; replace instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(prog="thedownloader", description=APP_NAME)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="check that ffmpeg, Deno, yt-dlp and Spotify are ready").set_defaults(func=cmd_check)
    sub.add_parser("init-config", help="create the settings file with default values").set_defaults(func=cmd_init_config)

    resolve = sub.add_parser("resolve", help="show what a link contains, without downloading")
    resolve.add_argument("link")
    resolve.add_argument("--show", type=int, default=10, help="how many items to list (default 10)")
    resolve.set_defaults(func=cmd_resolve)

    download = sub.add_parser("download", help="download a video or a whole playlist")
    download.add_argument("link")
    download.add_argument("--video", action="store_true", help="download video instead of audio only")
    download.add_argument("--audio-format", choices=["original", "mp3"], default="original")
    download.add_argument("--quality", choices=["best", "1080p", "720p"], default="best", help="video quality")
    download.add_argument("--limit", type=int, default=0, help="only download the first N items of a playlist")
    download.set_defaults(func=cmd_download)

    login = sub.add_parser("spotify-login", help="log in to Spotify in the browser")
    login.add_argument("--client-id", default="", help="client ID of your Spotify developer app (only needed once)")
    login.set_defaults(func=cmd_spotify_login)
    sub.add_parser("spotify-logout", help="delete the stored Spotify login").set_defaults(func=cmd_spotify_logout)

    match = sub.add_parser("match", help="show the YouTube Music matches for a song")
    match.add_argument("artist")
    match.add_argument("title")
    match.add_argument("--duration", type=int, default=0, help="song length in seconds, if known")
    match.add_argument("--show", type=int, default=6)
    match.set_defaults(func=cmd_match)

    args = parser.parse_args()
    sys.exit(args.func(args))
