"""Exception hierarchy for Scrawl.

Every error the package raises on purpose derives from ``ScrawlError`` so the
CLI can report it cleanly without swallowing unrelated bugs.
"""


class ScrawlError(Exception):
    """Base for all errors raised by this package."""


class ConfigurationError(ScrawlError):
    """The config file or one of its values is missing or invalid."""


class StorageError(ScrawlError):
    """A note or settings file could not be read or written."""


class IpcError(ScrawlError):
    """Talking to (or becoming) the single running instance failed."""


class ShellError(ScrawlError):
    """The Windows tray/hotkey shell could not be started."""
