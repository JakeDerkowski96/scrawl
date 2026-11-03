"""Tests for the single-instance socket protocol."""

import queue
import socket
from collections.abc import Iterator

import pytest

from scrawl.commands import Command
from scrawl.exceptions import IpcError
from scrawl.ipc import SingleInstanceServer, send_command


@pytest.fixture
def server() -> Iterator[tuple[SingleInstanceServer, "queue.Queue[Command]"]]:
    events: queue.Queue[Command] = queue.Queue()
    instance = SingleInstanceServer(0, events)  # port 0: let the OS pick a free one
    assert instance.start()
    yield instance, events
    instance.stop()


def test_command_is_delivered_to_the_queue(
    server: tuple[SingleInstanceServer, "queue.Queue[Command]"],
) -> None:
    instance, events = server
    send_command(instance.port, Command.NEW)
    assert events.get(timeout=2) == Command.NEW


def test_each_command_round_trips(
    server: tuple[SingleInstanceServer, "queue.Queue[Command]"],
) -> None:
    instance, events = server
    for command in Command:
        send_command(instance.port, command)
        assert events.get(timeout=2) == command


def test_second_server_on_same_port_does_not_start(
    server: tuple[SingleInstanceServer, "queue.Queue[Command]"],
) -> None:
    instance, _ = server
    rival = SingleInstanceServer(instance.port, queue.Queue())
    assert rival.start() is False


def test_port_is_released_after_stop() -> None:
    first = SingleInstanceServer(0, queue.Queue())
    assert first.start()
    port = first.port
    first.stop()
    second = SingleInstanceServer(port, queue.Queue())
    try:
        assert second.start() is True
    finally:
        second.stop()


def test_unknown_command_is_rejected_and_not_queued(
    server: tuple[SingleInstanceServer, "queue.Queue[Command]"],
) -> None:
    instance, events = server
    with socket.create_connection(("127.0.0.1", instance.port), timeout=2) as conn:
        conn.sendall(b"format-disk\n")
        assert conn.recv(64).startswith(b"scrawl error")
    assert events.empty()


def test_send_to_nothing_raises_ipc_error() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(IpcError, match="could not reach"):
        send_command(free_port, Command.SHOW, timeout=0.5)


def test_send_to_a_foreign_listener_is_detected() -> None:
    foreign = socket.socket()
    foreign.bind(("127.0.0.1", 0))
    foreign.listen(1)
    port = foreign.getsockname()[1]

    import threading

    def answer() -> None:
        conn, _ = foreign.accept()
        with conn:
            conn.recv(64)
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    try:
        with pytest.raises(IpcError, match="not Scrawl"):
            send_command(port, Command.SHOW, timeout=2)
    finally:
        thread.join(timeout=2)
        foreign.close()
