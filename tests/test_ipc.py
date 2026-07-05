"""Unit tests for the IPC framing + socket round-trip (Slice 1) and client-absent
handling (Slice 4)."""

from __future__ import annotations

import threading

import pytest

from whispr import ipc


def test_encode_decode_round_trips():
    message = {"cmd": "toggle", "note": "héllo"}
    assert ipc.decode(ipc.encode(message)) == message


def test_command_round_trips_over_socket(tmp_path):
    sock_path = tmp_path / "daemon.sock"
    seen: list[dict] = []

    def handler(command: dict) -> dict:
        seen.append(command)
        return {"status": "ok", "state": "RECORDING"}

    server = ipc.serve(sock_path)
    t = threading.Thread(target=ipc.handle_once, args=(server, handler))
    t.start()
    try:
        reply = ipc.send({"cmd": "toggle"}, sock_path)
    finally:
        t.join(timeout=5)
        server.close()

    assert seen == [{"cmd": "toggle"}]
    assert reply == {"status": "ok", "state": "RECORDING"}


def test_serve_unlinks_stale_socket(tmp_path):
    sock_path = tmp_path / "daemon.sock"
    sock_path.write_text("stale")  # a leftover file where the socket should bind
    server = ipc.serve(sock_path)
    server.close()  # bind succeeded despite the stale file


def test_send_reports_daemon_absent(tmp_path):
    sock_path = tmp_path / "nope.sock"  # nothing listening here
    with pytest.raises(ipc.DaemonUnavailable):
        ipc.send({"cmd": "toggle"}, sock_path)
