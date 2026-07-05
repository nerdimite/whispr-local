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


def poll_status(send=ipc.send, sock_path=ipc.DEFAULT_SOCK_PATH) -> dict | None:
    """Ask the Daemon for its status; return None if it isn't reachable.

    Swallows both `DaemonUnavailable` (nothing listening) and transient OSErrors so
    the indicator degrades to the "daemon not running" view instead of crashing.
    """
    try:
        return send({"cmd": "status"}, sock_path)
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
    quit_item = Gtk.MenuItem(label="Quit indicator")

    toggle_item.connect("activate", lambda _w: _send({"cmd": "toggle"}, sock_path))
    cancel_item.connect("activate", lambda _w: _send({"cmd": "cancel"}, sock_path))
    quit_item.connect("activate", lambda _w: Gtk.main_quit())

    for item in (header, Gtk.SeparatorMenuItem(), toggle_item, cancel_item,
                 Gtk.SeparatorMenuItem(), quit_item):
        menu.append(item)
    menu.show_all()
    indicator.set_menu(menu)

    def tick() -> bool:
        view = view_for(poll_status(sock_path=sock_path))
        indicator.set_icon_full(view.icon, view.label)
        header.set_label(f"whispr — {view.label}")
        # Cancel only makes sense mid-recording.
        cancel_item.set_sensitive(view.active)
        return True  # keep the timer alive

    tick()
    GLib.timeout_add(POLL_INTERVAL_MS, tick)
    Gtk.main()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(run_indicator())
