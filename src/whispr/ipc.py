"""Unix-domain-socket IPC between the `whispr` client commands and the Daemon.

Framing (`encode`/`decode`) is pure and unit-tested; `serve`/`send` are the thin
socket harness around it. A command is a JSON object `{"cmd": ...}`; a reply is a
JSON object `{"status": ..., "state"?: ..., "device"?: ...}`. One message per
connection, newline-terminated.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Callable

# Default socket location (XDG cache). The Daemon binds it; clients connect to it.
DEFAULT_SOCK_PATH = Path(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
) / "whispr" / "daemon.sock"


class DaemonUnavailable(Exception):
    """Raised by `send` when no Daemon is listening on the socket."""


def encode(message: dict) -> bytes:
    """Serialize a command or reply to a single newline-terminated JSON line."""
    return (json.dumps(message) + "\n").encode("utf-8")


def decode(data: bytes) -> dict:
    """Parse a framed message produced by `encode`."""
    text = data.decode("utf-8").strip()
    if not text:
        raise ValueError("empty message")
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError(f"expected a JSON object, got {type(result).__name__}")
    return result


def _recv_message(conn: socket.socket) -> dict:
    """Read one newline-framed message off a connected socket."""
    chunks: list[bytes] = []
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if chunk.endswith(b"\n"):
            break
    return decode(b"".join(chunks))


def serve(sock_path: str | os.PathLike) -> socket.socket:
    """Bind a listening Unix socket at `sock_path` and return it.

    Creates the parent directory and unlinks a stale socket file before binding.
    The caller drives `accept()` via `handle_once` (directly in tests, or on the
    GLib loop's read-ready callback in the Daemon).
    """
    path = Path(sock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(8)
    return server


def handle_once(server: socket.socket, handler: Callable[[dict], dict]) -> None:
    """Accept one connection, apply `handler`, write the reply back."""
    conn, _ = server.accept()
    try:
        command = _recv_message(conn)
        try:
            reply = handler(command)
        except Exception as exc:  # a handler bug must not kill the Daemon
            reply = {"status": "error", "error": str(exc)}
        conn.sendall(encode(reply))
    finally:
        conn.close()


def send(command: dict, sock_path: str | os.PathLike = DEFAULT_SOCK_PATH) -> dict:
    """Send one command to the Daemon and return its reply.

    Raises `DaemonUnavailable` (not a bare OSError) when nothing is listening, so
    callers can distinguish "daemon not running" from other failures.
    """
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        try:
            client.connect(str(sock_path))
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            raise DaemonUnavailable(str(sock_path)) from exc
        client.sendall(encode(command))
        return _recv_message(client)
    finally:
        client.close()
