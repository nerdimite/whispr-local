"""Unit tests for the status-bar Indicator's pure core: the status→view mapping
and the daemon polling helper. The GTK/Ayatana wiring in `run_indicator()` is an
untested harness (needs a live GLib loop + tray), same split as `run_daemon`."""

from __future__ import annotations

from whispr import indicator, ipc


def test_view_idle_shows_device():
    view = indicator.view_for({"status": "ok", "state": "IDLE", "device": "NPU"})
    assert view.label == "Idle · NPU"
    assert view.active is False
    assert view.icon == indicator.ICON_IDLE


def test_view_recording_is_active():
    view = indicator.view_for({"status": "ok", "state": "RECORDING", "device": "NPU"})
    assert view.label == "Recording…"
    assert view.active is True
    assert view.icon == indicator.ICON_RECORDING


def test_view_transcribing_is_active():
    view = indicator.view_for({"status": "ok", "state": "TRANSCRIBING", "device": "CPU"})
    assert view.label == "Transcribing…"
    assert view.active is True
    assert view.icon == indicator.ICON_TRANSCRIBING


def test_view_idle_without_device():
    view = indicator.view_for({"status": "ok", "state": "IDLE", "device": None})
    assert view.label == "Idle"


def test_view_daemon_down():
    view = indicator.view_for(None)
    assert view is indicator.VIEW_DOWN
    assert view.active is False
    assert "not running" in view.label.lower()


def test_poll_status_returns_reply():
    calls: list = []

    def fake_send(command, sock_path):
        calls.append((command, sock_path))
        return {"status": "ok", "state": "IDLE", "device": "NPU"}

    reply = indicator.poll_status(send=fake_send, sock_path="/tmp/x.sock")
    assert reply == {"status": "ok", "state": "IDLE", "device": "NPU"}
    assert calls == [({"cmd": "status"}, "/tmp/x.sock")]


def test_poll_status_maps_daemon_unavailable_to_none():
    def fake_send(command, sock_path):
        raise ipc.DaemonUnavailable("/tmp/x.sock")

    assert indicator.poll_status(send=fake_send, sock_path="/tmp/x.sock") is None


def test_poll_status_maps_oserror_to_none():
    def fake_send(command, sock_path):
        raise OSError("boom")

    assert indicator.poll_status(send=fake_send, sock_path="/tmp/x.sock") is None
