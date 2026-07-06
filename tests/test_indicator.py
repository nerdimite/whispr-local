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


# -- microphone submenu mapping ---------------------------------------------

def _devices_reply(current):
    return {
        "status": "ok",
        "current": current,
        "devices": [
            {"device": "alsa_input.builtin", "name": "Digital Microphone", "is_default": True},
            {"device": "bluez_input.jbl", "name": "JBL Tune 770NC", "is_default": False},
        ],
    }


def test_device_menu_leads_with_system_default():
    options = indicator.device_menu(_devices_reply(current="bluez_input.jbl"))
    assert options[0].label == "System default"
    assert options[0].device is None
    assert options[0].active is False  # a specific device is selected


def test_device_menu_marks_current_device_active():
    options = indicator.device_menu(_devices_reply(current="bluez_input.jbl"))
    labels = [o.label for o in options]
    assert labels == ["System default", "Digital Microphone (default)", "JBL Tune 770NC"]
    active = [o.label for o in options if o.active]
    assert active == ["JBL Tune 770NC"]
    # The device value carried back for set_device is the source name.
    assert options[2].device == "bluez_input.jbl"


def test_device_menu_default_selection_activates_system_default():
    options = indicator.device_menu(_devices_reply(current=None))
    assert options[0].active is True
    assert not any(o.active for o in options[1:])


def test_device_menu_matches_config_pinned_substring():
    # config.input_device can be a name fragment; it should still light up the full
    # source name it resolves to (and only that one).
    options = indicator.device_menu(_devices_reply(current="builtin"))
    active = [o.label for o in options if o.active]
    assert active == ["Digital Microphone (default)"]


def test_device_menu_empty_when_daemon_unreachable():
    assert indicator.device_menu(None) == []


def test_device_menu_empty_on_error_reply():
    assert indicator.device_menu({"status": "error", "error": "boom"}) == []


def test_poll_devices_maps_unavailable_to_none():
    def fake_send(command, sock_path):
        raise ipc.DaemonUnavailable("/tmp/x.sock")

    assert indicator.poll_devices(send=fake_send, sock_path="/tmp/x.sock") is None
