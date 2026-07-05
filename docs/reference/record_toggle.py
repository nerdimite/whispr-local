#!/usr/bin/env python3
"""
Toggle recording on/off. Bind this to a global hotkey.
First press: starts recording. Second press: stops and triggers transcription.
"""
import subprocess
import os
import signal
import time

LOCK_FILE = "/tmp/dictate.pid"
AUDIO_FILE = "/tmp/dictate.wav"
TRANSCRIBE_SCRIPT = os.path.expanduser("~/dictate/transcribe.py")


def start_recording():
    if os.path.exists(AUDIO_FILE):
        os.remove(AUDIO_FILE)
    proc = subprocess.Popen(
        ["arecord", "-f", "S16_LE", "-r", "16000", "-c", "1", AUDIO_FILE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(LOCK_FILE, "w") as f:
        f.write(str(proc.pid))
    subprocess.run(["notify-send", "Dictate", "Recording started"])


def stop_recording():
    with open(LOCK_FILE) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    os.remove(LOCK_FILE)
    subprocess.run(["notify-send", "Dictate", "Transcribing..."])
    time.sleep(0.3)
    subprocess.Popen(["python3", TRANSCRIBE_SCRIPT])


if __name__ == "__main__":
    if os.path.exists(LOCK_FILE):
        stop_recording()
    else:
        start_recording()
