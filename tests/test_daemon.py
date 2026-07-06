"""Daemon lifecycle tests (Slices 8–11).

Drives `Daemon.handle` directly with fakes for recorder/transcriber/injector — no
GLib loop, no socket, no hardware. Covers Toggle→State, the non-blocking worker
lifecycle, empty-transcript + cancel, and config-driven behavior.
"""

from __future__ import annotations

import threading

import numpy as np

from whispr import ipc
from whispr.daemon import Daemon


class FakeRecorder:
    def __init__(self, buffer=None, device=None):
        self.buffer = np.ones(8, dtype=np.float32) if buffer is None else buffer
        self.started = False
        self.stopped = False
        self.device = device

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        return self.buffer

    def set_device(self, device):
        self.device = device


class FakeTranscriber:
    def __init__(self, text="hello", active_device="CPU", gate=None):
        self.text = text
        self.active_device = active_device
        self.calls = 0
        self._gate = gate  # optional threading.Event to block on (non-blocking test)

    def transcribe(self, buffer):
        self.calls += 1
        if self._gate is not None:
            self._gate.wait(timeout=5)
        return self.text


class FakeInjector:
    def __init__(self):
        self.injected = []

    def inject(self, text):
        self.injected.append(text)


def make_daemon(recorder=None, transcriber=None, injector=None, notify=None, **kw):
    return Daemon(
        recorder or FakeRecorder(),
        transcriber or FakeTranscriber(),
        injector or FakeInjector(),
        notify=notify,
        **kw,
    )


# -- Slice 8: Toggle → State ------------------------------------------------

def test_two_toggles_advance_state():
    rec = FakeRecorder()
    # Block the transcriber so State stays TRANSCRIBING for the third-toggle check.
    gate = threading.Event()
    trans = FakeTranscriber(gate=gate)
    daemon = make_daemon(recorder=rec, transcriber=trans)

    assert daemon.handle({"cmd": "status"})["state"] == "IDLE"

    r1 = daemon.handle({"cmd": "toggle"})
    assert r1 == {"status": "ok", "state": "RECORDING", "device": "CPU"}
    assert rec.started
    assert daemon.handle({"cmd": "status"})["state"] == "RECORDING"

    r2 = daemon.handle({"cmd": "toggle"})
    assert r2["state"] == "TRANSCRIBING"
    assert rec.stopped

    # Third toggle while transcribing is rejected, State unchanged.
    r3 = daemon.handle({"cmd": "toggle"})
    assert r3["status"] == "busy"
    assert daemon.handle({"cmd": "status"})["state"] == "TRANSCRIBING"

    gate.set()
    if daemon._worker_thread:
        daemon._worker_thread.join(timeout=5)


def test_status_does_not_mutate_state():
    daemon = make_daemon()
    before = daemon.handle({"cmd": "status"})["state"]
    daemon.handle({"cmd": "status"})
    assert daemon.handle({"cmd": "status"})["state"] == before == "IDLE"


# -- Slice 9: full lifecycle on a worker thread -----------------------------

def test_dictation_end_to_end_with_fakes():
    rec = FakeRecorder(buffer=np.arange(4, dtype=np.float32))
    gate = threading.Event()
    trans = FakeTranscriber(text="hello", gate=gate)
    inj = FakeInjector()
    daemon = make_daemon(recorder=rec, transcriber=trans, injector=inj)

    daemon.handle({"cmd": "toggle"})  # -> RECORDING
    reply = daemon.handle({"cmd": "toggle"})  # -> TRANSCRIBING, dispatch worker

    # Non-blocking: the handler returned before the (gated) transcriber finished.
    assert reply["state"] == "TRANSCRIBING"
    assert inj.injected == []  # worker still blocked

    gate.set()
    daemon._worker_thread.join(timeout=5)

    assert inj.injected == ["hello"]
    assert daemon.state.name == "IDLE"


# -- Slice 10: empty transcript + cancel ------------------------------------

def test_empty_transcript_notifies_no_injection():
    notes = []
    trans = FakeTranscriber(text="")  # Whisper found no speech
    inj = FakeInjector()
    daemon = make_daemon(transcriber=trans, injector=inj, notify=notes.append)

    daemon.handle({"cmd": "toggle"})
    daemon.handle({"cmd": "toggle"})
    daemon._worker_thread.join(timeout=5)

    assert inj.injected == []  # nothing pasted
    assert any("no speech" in n.lower() for n in notes)
    assert daemon.state.name == "IDLE"


def test_silence_skips_transcription():
    # A near-silent capture must not reach the transcriber (else Whisper hallucinates
    # a phantom word). Peak 0 < default threshold 0.01 → "no speech", State IDLE.
    rec = FakeRecorder(buffer=np.zeros(16000, dtype=np.float32))
    trans = FakeTranscriber(text="you")
    inj = FakeInjector()
    notes = []
    daemon = make_daemon(recorder=rec, transcriber=trans, injector=inj, notify=notes.append)

    daemon.handle({"cmd": "toggle"})       # RECORDING
    reply = daemon.handle({"cmd": "toggle"})  # STOP → silence-gated

    assert reply["state"] == "IDLE"
    assert trans.calls == 0
    assert inj.injected == []
    assert daemon._worker_thread is None
    assert any("no speech" in n.lower() for n in notes)


def test_quiet_speech_with_loud_peak_passes_gate():
    # A Bluetooth-HFP-style capture: rms below silence_threshold (0.02) but with loud
    # transient peaks (> peak_threshold). The peak clause must let it transcribe
    # rather than dropping it as "no speech".
    buf = np.full(16000, 0.002, dtype=np.float32)
    buf[:20] = 0.12  # brief speech transients → peak 0.12, rms ~0.004
    rms = float(np.sqrt(np.mean(buf**2)))
    assert rms < 0.02  # would fail an rms-only gate
    rec = FakeRecorder(buffer=buf)
    trans = FakeTranscriber(text="hello")
    inj = FakeInjector()
    daemon = make_daemon(recorder=rec, transcriber=trans, injector=inj)

    daemon.handle({"cmd": "toggle"})
    daemon.handle({"cmd": "toggle"})
    daemon._worker_thread.join(timeout=5)

    assert trans.calls == 1
    assert inj.injected == ["hello"]


def test_cancel_discards_recording():
    rec = FakeRecorder()
    trans = FakeTranscriber()
    daemon = make_daemon(recorder=rec, transcriber=trans)

    daemon.handle({"cmd": "toggle"})  # -> RECORDING
    reply = daemon.handle({"cmd": "cancel"})  # -> IDLE, discard

    assert reply["state"] == "IDLE"
    assert rec.stopped
    assert trans.calls == 0  # transcriber never invoked
    assert daemon._worker_thread is None  # no worker spawned


# -- Slice 11: config-driven behavior ---------------------------------------

def test_notify_false_suppresses_notifications():
    # notify=None models a Daemon built from config with notify disabled.
    rec = FakeRecorder()
    trans = FakeTranscriber(text="")
    daemon = make_daemon(recorder=rec, transcriber=trans, notify=None)

    daemon.handle({"cmd": "toggle"})
    daemon.handle({"cmd": "toggle"})
    daemon._worker_thread.join(timeout=5)
    # No exception despite empty transcript + notify disabled.
    assert daemon.state.name == "IDLE"


def test_dump_last_recording_writes_wav(tmp_path):
    dump = tmp_path / "last_recording.wav"
    rec = FakeRecorder(buffer=np.linspace(-1, 1, 32, dtype=np.float32))
    daemon = make_daemon(recorder=rec, dump_recording_to=dump)

    daemon.handle({"cmd": "toggle"})
    daemon.handle({"cmd": "toggle"})
    daemon._worker_thread.join(timeout=5)

    assert dump.exists() and dump.stat().st_size > 44  # header + samples


class PeakCapturingTranscriber:
    """Records the peak amplitude of the buffer it's handed (to assert on gain)."""

    active_device = "CPU"

    def __init__(self):
        self.peak = None

    def transcribe(self, buffer):
        self.peak = float(np.abs(np.asarray(buffer, dtype=np.float32)).max())
        return "ok"


def test_quiet_capture_is_normalized_before_transcription():
    # A quiet-but-real capture (peak 0.1, rms 0.1 > threshold) should be lifted
    # toward full scale before Whisper sees it.
    rec = FakeRecorder(buffer=np.full(16000, 0.1, dtype=np.float32))
    trans = PeakCapturingTranscriber()
    daemon = make_daemon(recorder=rec, transcriber=trans)  # normalize on by default

    daemon.handle({"cmd": "toggle"})
    daemon.handle({"cmd": "toggle"})
    daemon._worker_thread.join(timeout=5)

    assert trans.peak is not None and trans.peak > 0.9


def test_normalization_can_be_disabled():
    rec = FakeRecorder(buffer=np.full(16000, 0.1, dtype=np.float32))
    trans = PeakCapturingTranscriber()
    daemon = make_daemon(recorder=rec, transcriber=trans, normalize_audio=False)

    daemon.handle({"cmd": "toggle"})
    daemon.handle({"cmd": "toggle"})
    daemon._worker_thread.join(timeout=5)

    assert trans.peak is not None and abs(trans.peak - 0.1) < 1e-4  # raw level preserved


def test_device_reported_from_transcriber():
    trans = FakeTranscriber(active_device="NPU")
    daemon = make_daemon(transcriber=trans)
    assert daemon.handle({"cmd": "status"})["device"] == "NPU"


# -- Microphone selection ----------------------------------------------------

def test_list_devices_reports_devices_and_current():
    devices = [
        {"device": "alsa_input.builtin", "name": "Built-in", "is_default": True},
        {"device": "bluez_input.jbl", "name": "USB mic", "is_default": False},
    ]
    rec = FakeRecorder(device="bluez_input.jbl")
    daemon = make_daemon(recorder=rec, list_devices=lambda: devices)

    reply = daemon.handle({"cmd": "list_devices"})
    assert reply == {"status": "ok", "devices": devices, "current": "bluez_input.jbl"}


def test_list_devices_without_enumerator_returns_empty():
    daemon = make_daemon(recorder=FakeRecorder(device=None))
    reply = daemon.handle({"cmd": "list_devices"})
    assert reply == {"status": "ok", "devices": [], "current": None}


def test_set_device_switches_recorder_when_idle():
    rec = FakeRecorder(device=None)
    daemon = make_daemon(recorder=rec)

    reply = daemon.handle({"cmd": "set_device", "device": 3})
    assert reply == {"status": "ok", "state": "IDLE", "current": 3}
    assert rec.device == 3


def test_set_device_rejected_while_recording():
    rec = FakeRecorder(device=1)
    daemon = make_daemon(recorder=rec)
    daemon.handle({"cmd": "toggle"})  # -> RECORDING

    reply = daemon.handle({"cmd": "set_device", "device": 7})
    assert reply["status"] == "busy"
    assert reply["current"] == 1  # unchanged
    assert rec.device == 1


# -- Rewrite stage (transcript → rewrite → inject, dictation-copilot) --------

def test_rewriter_output_is_injected():
    class FakeRewriter:
        def rewrite(self, transcript):
            return transcript.capitalize() + "."

    inj = FakeInjector()
    daemon = make_daemon(transcriber=FakeTranscriber(text="hello world"), injector=inj)
    daemon.rewriter = FakeRewriter()

    daemon.handle({"cmd": "toggle"})
    daemon.handle({"cmd": "toggle"})
    daemon._worker_thread.join(timeout=5)

    assert inj.injected == ["Hello world."]


def test_no_rewriter_injects_raw_transcript():
    inj = FakeInjector()
    daemon = make_daemon(transcriber=FakeTranscriber(text="raw"), injector=inj)

    daemon.handle({"cmd": "toggle"})
    daemon.handle({"cmd": "toggle"})
    daemon._worker_thread.join(timeout=5)

    assert inj.injected == ["raw"]


# -- Integration: the client → socket → Daemon.handle path (tracer bullet) --

def test_toggle_round_trips_through_socket(tmp_path):
    sock_path = tmp_path / "daemon.sock"
    daemon = make_daemon(transcriber=FakeTranscriber(active_device="NPU"))
    server = ipc.serve(sock_path)
    t = threading.Thread(target=ipc.handle_once, args=(server, daemon.handle))
    t.start()
    try:
        reply = ipc.send({"cmd": "toggle"}, sock_path)  # what `whispr toggle` sends
    finally:
        t.join(timeout=5)
        server.close()
    assert reply == {"status": "ok", "state": "RECORDING", "device": "NPU"}
