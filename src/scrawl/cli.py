"""Command-line interface for Scrawl.

Required permissions: none beyond those of the subcommand (see README).

Usage:
    scrawl                         # start the app, or focus it if running
    scrawl run --hidden            # start quietly in the tray
    scrawl new                     # open a fresh note (starting the app if needed)
    scrawl show | quit             # control the running app
    scrawl add "call the dentist"  # append a note without opening the window
    echo "idea" | scrawl add       # ... or from a pipe
    scrawl add --dry-run "test"    # show what would be written
    scrawl list -n 10              # recent notes
    scrawl search milk eggs        # notes containing both words
    scrawl autostart enable        # start at login
    scrawl config                  # show the config path and effective settings

Notes:
    This module only parses arguments and sets up logging; behavior lives in
    the other modules. Results go to stdout, diagnostics to the log.
"""

import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from logging.handlers import RotatingFileHandler

from scrawl import __version__, autostart
from scrawl.commands import Command
from scrawl.config import LOG_FILENAME, Config, config_dir, load_config
from scrawl.exceptions import ScrawlError
from scrawl.ipc import send_command
from scrawl.search import search_notes
from scrawl.store import Note, NoteStore

logger = logging.getLogger("scrawl")

_LOG_BYTES = 256 * 1024
_LOG_BACKUPS = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="scrawl", description="A tiny, fast notepad with a global hotkey."
    )
    parser.add_argument("--version", action="version", version=f"scrawl {__version__}")
    _add_common(parser, suppress=False)
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="start the app (default), or focus it if already running")
    _add_common(run)
    run.add_argument("--hidden", action="store_true", help="start in the tray without a window")
    run.set_defaults(handler=_cmd_run)

    new = sub.add_parser("new", help="open a fresh note in the running (or a new) app")
    _add_common(new)
    new.set_defaults(handler=_cmd_new)

    show = sub.add_parser("show", help="bring the running app's window to the front")
    _add_common(show)
    show.set_defaults(handler=_cmd_show)

    quit_ = sub.add_parser("quit", help="ask the running app to save and exit")
    _add_common(quit_)
    quit_.set_defaults(handler=_cmd_quit)

    add = sub.add_parser("add", help="create a note from text (arguments or stdin)")
    _add_common(add)
    add.add_argument("text", nargs="*", help="note text; read from stdin if omitted")
    add.set_defaults(handler=_cmd_add)

    list_ = sub.add_parser("list", help="list notes, newest first")
    _add_common(list_)
    list_.add_argument("-n", "--limit", type=int, default=20, help="how many to show (default 20)")
    list_.set_defaults(handler=_cmd_list)

    search = sub.add_parser("search", help="list notes containing all given words")
    _add_common(search)
    search.add_argument("terms", nargs="+", help="words to look for")
    search.add_argument("-n", "--limit", type=int, default=20, help="how many to show")
    search.set_defaults(handler=_cmd_search)

    auto = sub.add_parser("autostart", help="manage start-at-login")
    _add_common(auto)
    auto.add_argument("action", choices=("enable", "disable", "status"))
    auto.set_defaults(handler=_cmd_autostart)

    config = sub.add_parser("config", help="show the config file path and effective settings")
    _add_common(config)
    config.set_defaults(handler=_cmd_config)
    return parser


def _add_common(parser: argparse.ArgumentParser, *, suppress: bool = True) -> None:
    """Add flags that work both before and after the subcommand.

    Subparser defaults are suppressed so a flag given before the subcommand is
    not overwritten by the subparser's own default.
    """
    default = argparse.SUPPRESS if suppress else False
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=default, help="show debug detail"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=default,
        help="report what would change without changing anything",
    )


def setup_logging(*, verbose: bool, to_file: bool) -> None:
    """Configure logging.

    Args:
        verbose: Include debug messages.
        to_file: Also log to the rotating file in the config folder (the app
            itself runs without a console, so the file is its only record).
    """
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    if sys.stderr is not None:  # None when launched via pythonw / the gui script
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.DEBUG if verbose else logging.WARNING)
        console.setFormatter(formatter)
        logger.addHandler(console)

    if to_file:
        try:
            config_dir().mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                config_dir() / LOG_FILENAME,
                maxBytes=_LOG_BYTES,
                backupCount=_LOG_BACKUPS,
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("could not open the log file: %s", exc)
            return
        handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        handler.setFormatter(formatter)
        logger.addHandler(handler)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = getattr(args, "handler", _cmd_run)
    if not hasattr(args, "hidden"):
        args.hidden = False

    setup_logging(verbose=args.verbose, to_file=handler is _cmd_run or handler is _cmd_new)
    try:
        return handler(args)
    except ScrawlError as exc:
        logger.error("%s", exc)
        _report_error(str(exc))
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # Last resort: record the traceback (the GUI has no console) and tell the user.
        logger.exception("unexpected error")
        _report_error(f"unexpected error: {exc}")
        return 1


def gui_main() -> int:
    """Entry point for the console-less ``scrawl-gui`` launcher."""
    return main(["run", *sys.argv[1:]])


def _report_error(message: str) -> None:
    """Tell the user about a failure, via stderr or (without a console) a dialog."""
    if sys.stderr is not None:
        sys.stderr.write(f"scrawl: error: {message}\n")
    else:
        from scrawl import winutil

        winutil.show_error("Scrawl", message)


def _load(*, write_defaults: bool = False) -> Config:
    return load_config(write_defaults=write_defaults)


# --------------------------------------------------------------------- handlers


def _cmd_run(args: argparse.Namespace) -> int:
    from scrawl.app import run_app

    return run_app(_load(write_defaults=True), hidden=args.hidden, initial=None)


def _cmd_new(args: argparse.Namespace) -> int:  # noqa: ARG001 - uniform handler signature
    from scrawl.app import run_app

    return run_app(_load(write_defaults=True), hidden=False, initial=Command.NEW)


def _cmd_show(args: argparse.Namespace) -> int:  # noqa: ARG001
    send_command(_load().ipc_port, Command.SHOW)
    return 0


def _cmd_quit(args: argparse.Namespace) -> int:  # noqa: ARG001
    send_command(_load().ipc_port, Command.QUIT)
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    text = " ".join(args.text)
    if not text:
        if sys.stdin is None or sys.stdin.isatty():
            raise ScrawlError("nothing to add: pass text as arguments or pipe it in")
        text = sys.stdin.read()
    text = text.strip("\n")
    if not text.strip():
        raise ScrawlError("nothing to add: the text is empty")

    store = NoteStore(_load().notes_dir)
    note = store.create(text + "\n", dry_run=args.dry_run)
    verb = "would create" if args.dry_run else "created"
    print(f"{verb} {note.path}")
    return 0


def _format_note(note: Note) -> str:
    stamp = datetime.fromtimestamp(note.modified).strftime("%Y-%m-%d %H:%M")
    return f"{note.id}\t{stamp}\t{note.title}"


def _cmd_list(args: argparse.Namespace) -> int:
    for note in NoteStore(_load().notes_dir).list_notes()[: args.limit]:
        print(_format_note(note))
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    store = NoteStore(_load().notes_dir)
    for note in search_notes(store, " ".join(args.terms))[: args.limit]:
        print(_format_note(note))
    return 0


def _cmd_autostart(args: argparse.Namespace) -> int:
    if args.action == "enable":
        print(autostart.enable(dry_run=args.dry_run))
    elif args.action == "disable":
        print(autostart.disable(dry_run=args.dry_run))
    else:
        print("enabled" if autostart.is_enabled() else "disabled")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:  # noqa: ARG001
    path = config_dir()
    print(f"config folder: {path}")
    print(f"config file:   {path / 'config.json'}")
    print(json.dumps(_load().to_json_dict(), indent=2))
    return 0
