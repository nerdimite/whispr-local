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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whispr", description="On-device Whisper dictation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("daemon", help="run the resident Daemon")
    sub.add_parser("toggle", help="start/stop a Dictation (the hotkey target)")
    sub.add_parser("status", help="print State + active device")
    sub.add_parser("cancel", help="drop an in-progress Recording")

    args = parser.parse_args(argv)

    if args.command == "daemon":
        from .daemon import run_daemon

        return run_daemon()
    return _send_command(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
