"""Status-bar indicator for whispr (MVP-1).

A standalone tray icon (StatusNotifierItem via Ayatana AppIndicator) that reflects
the Daemon's live state and offers Toggle/Cancel from its menu. It is a SEPARATE
process from the Daemon: it talks over the same Unix socket (`whispr.ipc`), polling
`status` on a timer and sending `toggle`/`cancel` on menu clicks. This keeps the
Daemon pristine and GLib-free (see docs/design/v1_design.md decision #6/#14).

Because it needs GTK/GLib/gi, it runs under the SYSTEM python (`/usr/bin/python3`,
which has python3-gi + gir1.2-ayatanaappindicator3-0.1), NOT the lean inference
venv. Only `whispr.ipc` is imported here, and that is pure stdlib, so system python
can import this package via PYTHONPATH=<repo>/src with nothing else installed.

Split for testability (mirrors daemon.py):
- Pure core — `view_for()` (status dict → IndicatorView) and `poll_status()` — is
  unit-tested with fakes, no gi.
- `run_indicator()` is the thin production harness that owns the GTK objects and the
  GLib main loop; it is not unit-tested (needs a live tray + loop).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import ipc

# Themed symbolic icon names (resolved from the active GTK icon theme; Adwaita has
# all of these). Kept as constants so tests assert on them without hardcoding.
ICON_IDLE = "audio-input-microphone-symbolic"
ICON_RECORDING = "media-record-symbolic"
ICON_TRANSCRIBING = "content-loading-symbolic"
ICON_DOWN = "microphone-sensitivity-muted-symbolic"

POLL_INTERVAL_MS = 250
# Refresh the microphone list every this-many status ticks (~2s at 250ms).
MIC_REFRESH_EVERY = 8


@dataclass(frozen=True)
class IndicatorView:
    """What the tray should show for a given Daemon state. Pure data — the harness
    maps this onto the AppIndicator/menu widgets."""

    icon: str
    label: str
    active: bool  # True while recording/transcribing → use the "attention" icon


VIEW_DOWN = IndicatorView(icon=ICON_DOWN, label="whispr — daemon not running", active=False)

_ICONS = {
    "IDLE": ICON_IDLE,
    "RECORDING": ICON_RECORDING,
    "TRANSCRIBING": ICON_TRANSCRIBING,
}


def _label(state: str, device) -> str:
    if state == "RECORDING":
        return "Recording…"
    if state == "TRANSCRIBING":
        return "Transcribing…"
    if state == "IDLE":
        return f"Idle · {device}" if device else "Idle"
    return state or "unknown"


def view_for(status: dict | None) -> IndicatorView:
    """Map a `status` reply (or None when the Daemon is unreachable) to a view."""
    if not status:
        return VIEW_DOWN
    state = status.get("state")
    device = status.get("device")
    return IndicatorView(
        icon=_ICONS.get(state, ICON_IDLE),
        label=_label(state, device),
        active=state in ("RECORDING", "TRANSCRIBING"),
    )


@dataclass(frozen=True)
class MicOption:
    """One entry in the microphone submenu. Pure data — the harness maps it onto a
    radio menu item. `device` is what to send back as `set_device`'s device: None
    for the system default, else a device identifier (a PipeWire source name or an
    int index) the daemon's recorder understands."""

    label: str
    device: object
    active: bool


def _is_current(current, device) -> bool:
    """Is `device` the one the daemon reports as current?

    Exact match, plus a substring tolerance so a config-pinned name fragment (e.g.
    "HiFi__Mic__source") still lights up the full source name it selects."""
    if current is None or device is None:
        return current is None and device is None
    if current == device:
        return True
    return isinstance(current, str) and isinstance(device, str) and current in device


def device_menu(reply: dict | None) -> list[MicOption]:
    """Map a `list_devices` reply to the microphone submenu options.

    Always leads with a "System default" entry (device=None), then one entry per
    input device. The option matching the daemon's reported `current` is marked
    active. Returns [] when the daemon is unreachable or errored, so the harness can
    show a disabled placeholder instead of a misleading empty list.
    """
    if not reply or reply.get("status") != "ok":
        return []
    current = reply.get("current")
    matched = False
    options = [MicOption(label="System default", device=None, active=current is None)]
    for entry in reply.get("devices", []):
        device = entry.get("device")
        name = entry.get("name", str(device))
        suffix = " (default)" if entry.get("is_default") else ""
        active = not matched and _is_current(current, device)
        matched = matched or active
        options.append(MicOption(label=f"{name}{suffix}", device=device, active=active))
    return options


def poll_status(send=ipc.send, sock_path=ipc.DEFAULT_SOCK_PATH) -> dict | None:
    """Ask the Daemon for its status; return None if it isn't reachable.

    Swallows both `DaemonUnavailable` (nothing listening) and transient OSErrors so
    the indicator degrades to the "daemon not running" view instead of crashing.
    """
    try:
        return send({"cmd": "status"}, sock_path)
    except (ipc.DaemonUnavailable, OSError):
        return None


def poll_devices(send=ipc.send, sock_path=ipc.DEFAULT_SOCK_PATH) -> dict | None:
    """Ask the Daemon for its capture-device list; None if it isn't reachable."""
    try:
        return send({"cmd": "list_devices"}, sock_path)
    except (ipc.DaemonUnavailable, OSError):
        return None


def _send(command: dict, sock_path=ipc.DEFAULT_SOCK_PATH) -> None:
    """Fire a command at the Daemon, ignoring failures (menu clicks are best-effort)."""
    try:
        ipc.send(command, sock_path)
    except (ipc.DaemonUnavailable, OSError):
        pass


# -- production harness (untested; needs gi + a live GLib loop) ----------------
def run_indicator(sock_path=ipc.DEFAULT_SOCK_PATH) -> int:
    """Build the AppIndicator, wire its menu, and run the GTK main loop.

    Polls the Daemon every POLL_INTERVAL_MS and repaints the icon/menu. Runs under
    system python (needs gi); imported lazily so the module stays import-safe (and
    unit-testable) in the venv where gi is absent.
    """
    import gi

    gi.require_version("Gtk", "3.0")
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator
    except (ValueError, ImportError):  # older systems ship the non-Ayatana name
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AppIndicator

    from gi.repository import GLib, Gtk

    indicator = AppIndicator.Indicator.new(
        "whispr",
        ICON_IDLE,
        AppIndicator.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

    menu = Gtk.Menu()
    header = Gtk.MenuItem(label="whispr")
    header.set_sensitive(False)
    toggle_item = Gtk.MenuItem(label="Start / stop dictation")
    cancel_item = Gtk.MenuItem(label="Cancel recording")
    mic_item = Gtk.MenuItem(label="Microphone")
    mic_menu = Gtk.Menu()
    mic_item.set_submenu(mic_menu)
    quit_item = Gtk.MenuItem(label="Quit indicator")

    toggle_item.connect("activate", lambda _w: _send({"cmd": "toggle"}, sock_path))
    cancel_item.connect("activate", lambda _w: _send({"cmd": "cancel"}, sock_path))
    quit_item.connect("activate", lambda _w: Gtk.main_quit())

    for item in (header, Gtk.SeparatorMenuItem(), toggle_item, cancel_item,
                 mic_item, Gtk.SeparatorMenuItem(), quit_item):
        menu.append(item)
    menu.show_all()
    indicator.set_menu(menu)

    # `sig` short-circuits rebuilds when the device set/selection is unchanged (the
    # common case) so we don't churn radio widgets under an open menu. `building`
    # suppresses the `toggled` handler while we programmatically set_active.
    mic_state = {"sig": None, "building": False, "ticks": 0}

    def on_mic_toggled(widget, device) -> None:
        if mic_state["building"] or not widget.get_active():
            return
        _send({"cmd": "set_device", "device": device}, sock_path)

    def refresh_mic_menu() -> None:
        options = device_menu(poll_devices(sock_path=sock_path))
        sig = tuple((o.label, o.active) for o in options)
        if sig == mic_state["sig"]:
            return
        mic_state["sig"] = sig
        mic_state["building"] = True
        try:
            for child in mic_menu.get_children():
                mic_menu.remove(child)
            if not options:
                placeholder = Gtk.MenuItem(label="daemon not running")
                placeholder.set_sensitive(False)
                mic_menu.append(placeholder)
            else:
                group = None
                for opt in options:
                    radio = Gtk.RadioMenuItem.new_with_label([], opt.label)
                    if group is None:
                        group = radio
                    else:
                        radio.join_group(group)
                    radio.set_active(opt.active)
                    radio.connect("toggled", on_mic_toggled, opt.device)
                    mic_menu.append(radio)
            mic_menu.show_all()
        finally:
            mic_state["building"] = False

    def tick() -> bool:
        view = view_for(poll_status(sock_path=sock_path))
        indicator.set_icon_full(view.icon, view.label)
        header.set_label(f"whispr — {view.label}")
        # Cancel only makes sense mid-recording.
        cancel_item.set_sensitive(view.active)
        # Switching mics is only allowed at IDLE (the daemon rejects it otherwise).
        mic_item.set_sensitive(not view.active)
        # Device set changes rarely; enumerating it (sd.query_devices in the daemon)
        # every 250ms poll is wasteful, so refresh the mic list only every ~2s.
        if mic_state["ticks"] % MIC_REFRESH_EVERY == 0:
            refresh_mic_menu()
        mic_state["ticks"] += 1
        return True  # keep the timer alive

    tick()
    GLib.timeout_add(POLL_INTERVAL_MS, tick)
    Gtk.main()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(run_indicator())
