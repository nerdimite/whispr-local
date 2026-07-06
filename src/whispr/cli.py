"""`whispr` console entry point: daemon | toggle | status | cancel.

`toggle`/`status`/`cancel` are thin clients — they send one command over the socket
and act on the reply. `daemon` runs the resident process (wired in the daemon slices).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from . import ipc


def _notify(message: str) -> None:
    """Best-effort desktop notification; never raises (notify-send may be absent)."""
    try:
        subprocess.run(["notify-send", "whispr", message], check=False)
    except FileNotFoundError:
        pass


def _send_command(cmd: str) -> int:
    """Send a client command; map a missing Daemon to a notification + exit 1."""
    try:
        reply = ipc.send({"cmd": cmd})
    except ipc.DaemonUnavailable:
        _notify("daemon not running")
        print("whispr: daemon not running", file=sys.stderr)
        return 1
    status = reply.get("status")
    if cmd == "status":
        print(f"state={reply.get('state')} device={reply.get('device')}")
    elif status == "busy":
        _notify("busy — transcribing")
    return 0


def _list_devices() -> int:
    """Print the daemon's capture devices, marking the current and default ones."""
    try:
        reply = ipc.send({"cmd": "list_devices"})
    except ipc.DaemonUnavailable:
        print("whispr: daemon not running", file=sys.stderr)
        return 1
    if reply.get("status") != "ok":
        print(f"whispr: {reply.get('error', 'could not list devices')}", file=sys.stderr)
        return 1
    current = reply.get("current")

    def is_current(device) -> bool:
        # Mirror the tray's tolerant match: exact, or a config-pinned name fragment
        # that resolves to this full source name.
        if current == device:
            return True
        return isinstance(current, str) and isinstance(device, str) and current in device

    matched = False
    print(f"  {'*' if current is None else ' '} default   (system default)")
    for entry in reply.get("devices", []):
        device = entry.get("device")
        mark = "*" if not matched and is_current(device) else " "
        matched = matched or mark == "*"
        tags = " (default)" if entry.get("is_default") else ""
        print(f"  {mark} {entry.get('name', '')}{tags}")
        print(f"      set-device {device!r}")
    return 0


def _set_device(value: str) -> int:
    """Switch the daemon's capture device. `value` is 'default', a device index, or a
    source-name substring (see `whispr devices`)."""
    if value.lower() == "default":
        device = None
    elif value.lstrip("-").isdigit():
        device = int(value)
    else:
        device = value
    try:
        reply = ipc.send({"cmd": "set_device", "device": device})
    except ipc.DaemonUnavailable:
        print("whispr: daemon not running", file=sys.stderr)
        return 1
    status = reply.get("status")
    if status == "ok":
        print(f"whispr: capture device set to {reply.get('current')!r}")
        return 0
    if status == "busy":
        print("whispr: busy — can't switch microphone now", file=sys.stderr)
        return 1
    print(f"whispr: {reply.get('error', 'could not set device')}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whispr", description="On-device Whisper dictation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("daemon", help="run the resident Daemon")
    sub.add_parser("toggle", help="start/stop a Dictation (the hotkey target)")
    sub.add_parser("status", help="print State + active device")
    sub.add_parser("cancel", help="drop an in-progress Recording")
    sub.add_parser("devices", help="list capture devices (marks the current one)")
    set_dev = sub.add_parser("set-device", help="switch capture device")
    set_dev.add_argument("device", help="'default' or a device index (see `whispr devices`)")

    args = parser.parse_args(argv)

    if args.command == "daemon":
        from .daemon import run_daemon

        return run_daemon()
    if args.command == "devices":
        return _list_devices()
    if args.command == "set-device":
        return _set_device(args.device)
    return _send_command(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
