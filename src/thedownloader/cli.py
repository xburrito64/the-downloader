"""Terminal entry point. Used to test each milestone before the UI exists."""

import argparse
import sys

from . import APP_NAME, config, paths, startup


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="thedownloader", description=APP_NAME)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="check that ffmpeg, Deno, yt-dlp and Spotify are ready").set_defaults(func=cmd_check)
    sub.add_parser("init-config", help="create the settings file with default values").set_defaults(func=cmd_init_config)
    args = parser.parse_args()
    sys.exit(args.func(args))
