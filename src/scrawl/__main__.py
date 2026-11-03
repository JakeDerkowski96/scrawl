"""Entry point for ``python -m scrawl``.

Usage:
    python -m scrawl            # start (or focus) the app
    python -m scrawl list       # any CLI subcommand works
"""

from scrawl.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
