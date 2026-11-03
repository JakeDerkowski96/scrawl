"""Single-instance enforcement and remote control over a loopback socket.

Required permissions: none. Binds ``127.0.0.1`` only; nothing is reachable from
the network.

Usage:
    server = SingleInstanceServer(port, events)
    if server.start():
        ...                              # we are the running instance
    else:
        send_command(port, Command.SHOW)  # tell the running instance instead

Notes:
    Holding the listening port *is* the single-instance lock: the OS releases
    it automatically if the process dies, so there is no stale lock file to
    clean up. Any local process can send ``show``/``new``/``toggle``/``quit``;
    that is acceptable for a single-user desktop notepad, and the commands can
    never read or change note content. See ``docs/architecture.md``.
"""

import logging
import queue
import socket
import sys
import threading

from scrawl.commands import Command
from scrawl.exceptions import IpcError

logger = logging.getLogger(__name__)

_REPLY_OK = b"scrawl ok\n"
_REPLY_PREFIX = b"scrawl "
_ACCEPT_TIMEOUT_S = 0.25
_CONN_TIMEOUT_S = 1.0
_MAX_REQUEST = 64


class SingleInstanceServer:
    """Listens for commands from later launches and feeds them to the UI queue."""

    def __init__(self, port: int, events: "queue.Queue[Command]") -> None:
        self._requested_port = port
        self._events = events
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def port(self) -> int:
        """The bound port (useful when started with port 0 in tests)."""
        if self._sock is None:
            return self._requested_port
        return int(self._sock.getsockname()[1])

    def start(self) -> bool:
        """Try to become the running instance.

        Returns:
            True if this process now holds the port; False if another process
            already does.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform == "win32":
            # Stops another process from sharing the port, which would defeat
            # the single-instance guarantee.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", self._requested_port))
            sock.listen(4)
        except OSError as exc:
            sock.close()
            logger.debug("port %d unavailable: %s", self._requested_port, exc)
            return False
        sock.settimeout(_ACCEPT_TIMEOUT_S)
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, name="scrawl-ipc", daemon=True)
        self._thread.start()
        logger.info("listening for commands on 127.0.0.1:%d", self.port)
        return True

    def stop(self) -> None:
        """Stop serving and release the port."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _serve(self) -> None:
        """Accept loop; runs on a background thread."""
        sock = self._sock
        assert sock is not None  # noqa: S101 - set just before the thread starts
        while not self._stop.is_set():
            try:
                conn, _ = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                if not self._stop.is_set():
                    logger.exception("ipc accept failed; command channel is down")
                return
            with conn:
                self._handle(conn)

    def _handle(self, conn: socket.socket) -> None:
        """Read one command from ``conn``, queue it, and reply."""
        conn.settimeout(_CONN_TIMEOUT_S)
        try:
            raw = conn.recv(_MAX_REQUEST).decode("utf-8", errors="replace").strip()
            if not raw:
                # A bare connect-and-close is a liveness probe, not a command.
                logger.debug("ipc probe (empty request)")
                return
            try:
                command = Command(raw)
            except ValueError:
                logger.warning("ignoring unknown ipc command %r", raw[:20])
                conn.sendall(b"scrawl error unknown command\n")
                return
            self._events.put(command)
            conn.sendall(_REPLY_OK)
        except OSError as exc:
            logger.warning("ipc connection failed: %s", exc)


def send_command(port: int, command: Command, *, timeout: float = 2.0) -> None:
    """Send ``command`` to the running instance.

    Raises:
        IpcError: If nothing is listening, or the listener is not Scrawl.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
            conn.sendall(f"{command.value}\n".encode())
            reply = conn.recv(_MAX_REQUEST)
    except OSError as exc:
        raise IpcError(f"could not reach a running Scrawl on port {port}: {exc}") from exc
    if not reply.startswith(_REPLY_PREFIX):
        raise IpcError(
            f"port {port} is in use by another program (not Scrawl). "
            "Change 'ipc_port' in config.json."
        )
    if reply != _REPLY_OK:
        raise IpcError(f"running instance rejected {command.value!r}: {reply!r}")
