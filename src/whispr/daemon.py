"""The resident whispr Daemon: GLib loop + Unix socket server + worker-thread
dispatch, wiring the pure State machine to the recorder/transcriber/injector.

The Daemon is split so its decision logic is testable without a live GLib loop or
hardware: `Daemon.handle(command)` is a plain method driven directly in tests with
fake collaborators. `run_daemon()` is the thin production harness that owns the GLib
main loop and the socket accept watch.

Invariants (see docs/design/v1_design.md):
- State mutation stays single-threaded: the blocking `transcribe` + `inject` run on a
  worker thread, which posts `complete` back to the loop thread to advance to IDLE.
- The socket handler never blocks — `STOP_AND_DISPATCH` returns immediately after
  spawning the worker.
- Device is decided once (in the Transcriber) and reported via `status`.
"""

from __future__ import annotations

import threading
import traceback
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import ipc
from .state import Effect, Event, State, transition


def _write_wav(path: Path, buffer: np.ndarray) -> None:
    """Dump a 16 kHz mono float32 buffer to a 16-bit PCM WAV (debug aid)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(np.asarray(buffer, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())


class Daemon:
    """Holds the current State and maps socket commands onto collaborators.

    Collaborators (recorder/transcriber/injector) and the two scheduling seams
    (`spawn` for the worker thread, `post` to hop back to the loop thread) are all
    injected so the whole lifecycle is exercisable with fakes.
    """

    def __init__(
        self,
        recorder,
        transcriber,
        injector,
        rewriter=None,
        notify: Optional[Callable[[str], None]] = None,
        dump_recording_to: Optional[Path] = None,
        silence_threshold: float = 0.02,
        spawn: Optional[Callable[[Callable[[], None]], None]] = None,
        post: Optional[Callable[[Callable[[], None]], None]] = None,
    ):
        self.state = State.IDLE
        self.recorder = recorder
        self.transcriber = transcriber
        self.injector = injector
        # Optional dictation-copilot rewrite stage (transcript → rewrite → inject).
        # The Rewriter client itself falls back to the raw transcript on any
        # failure, so this seam can never lose a dictation.
        self.rewriter = rewriter
        self._notify = notify
        self._dump_recording_to = dump_recording_to
        # Below this peak amplitude the capture is effectively silence; skip it so
        # Whisper doesn't hallucinate a phantom word ("you", "Thank you.") from noise.
        self._silence_threshold = silence_threshold
        self._spawn = spawn or self._default_spawn
        # Default `post` runs the callback inline (worker thread); a `_lock` keeps
        # State mutation safe when the worker's completion races an incoming command.
        self._post = post or (lambda fn: fn())
        self._lock = threading.RLock()
        self._worker_thread: Optional[threading.Thread] = None

    # -- seams -------------------------------------------------------------
    def _default_spawn(self, fn: Callable[[], None]) -> None:
        self._worker_thread = threading.Thread(target=fn, daemon=True)
        self._worker_thread.start()

    def _device(self) -> Optional[str]:
        return getattr(self.transcriber, "active_device", None)

    def _emit(self, message: str) -> None:
        if callable(self._notify):
            self._notify(message)

    # -- command handling --------------------------------------------------
    def handle(self, command: dict) -> dict:
        """Socket entry point: map a command to a State transition + reply."""
        cmd = command.get("cmd")
        if cmd == "status":
            with self._lock:
                return {"status": "ok", "state": self.state.name, "device": self._device()}
        event = {"toggle": Event.TOGGLE, "cancel": Event.CANCEL}.get(cmd)
        if event is None:
            return {"status": "error", "error": f"unknown command: {cmd!r}"}
        with self._lock:
            return self._apply(event)

    def _apply(self, event: Event) -> dict:
        next_state, effect = transition(self.state, event)
        if effect is Effect.REJECT_BUSY:
            self._emit("busy — transcribing")
            return {"status": "busy", "state": self.state.name, "device": self._device()}

        self.state = next_state
        if effect is Effect.START_RECORDING:
            try:
                self.recorder.start()
            except Exception as exc:  # mic unavailable → don't strand State in RECORDING
                self.state = State.IDLE
                traceback.print_exc()
                self._emit(f"cannot record: {exc}")
                return {"status": "error", "error": str(exc), "state": self.state.name}
            print("whispr: recording…", flush=True)
            self._emit("recording")
        elif effect is Effect.STOP_AND_DISPATCH:
            buffer = self.recorder.stop()
            n = int(getattr(buffer, "shape", [0])[0])
            arr = np.asarray(buffer, dtype=np.float32)
            peak = float(np.abs(arr).max()) if n else 0.0
            rms = float(np.sqrt(np.mean(arr**2))) if n else 0.0
            print(
                f"whispr: captured {n} samples ({n / 16000:.1f}s), rms={rms:.4f} peak={peak:.3f}",
                flush=True,
            )
            if self._dump_recording_to is not None:
                _write_wav(self._dump_recording_to, buffer)
            if rms < self._silence_threshold:
                # RMS below threshold ⇒ effectively silence; skip transcription so
                # Whisper can't hallucinate a phantom word. Tune via config.silence_threshold
                # using the logged rms of a real utterance vs. ambient.
                print(f"whispr: rms {rms:.4f} < {self._silence_threshold} — no speech", flush=True)
                self._emit("no speech detected")
                self.state = State.IDLE
                return {"status": "ok", "state": self.state.name, "device": self._device()}
            self._emit("transcribing")
            self._spawn(lambda: self._worker(buffer))
        elif effect is Effect.DISCARD:
            self.recorder.stop()  # drop the buffer; no transcription
            print("whispr: recording discarded", flush=True)

        return {"status": "ok", "state": self.state.name, "device": self._device()}

    # -- worker thread -----------------------------------------------------
    def _worker(self, buffer) -> None:
        """Runs on a worker thread: transcribe, deliver, then post completion.

        A failure here must NOT strand State in TRANSCRIBING — `finally` always posts
        `complete` so the Daemon returns to IDLE and the next Toggle works.
        """
        try:
            transcript = self.transcriber.transcribe(buffer)
            print(f"whispr: transcript={transcript!r}", flush=True)
            self._deliver(transcript)
        except Exception as exc:
            traceback.print_exc()
            self._emit(f"transcription failed: {exc}")
        finally:
            self._post(self._finish)

    def _deliver(self, transcript: str) -> None:
        if transcript and self.rewriter is not None:
            rewritten = self.rewriter.rewrite(transcript)
            if rewritten != transcript:
                print(f"whispr: rewritten={rewritten!r}", flush=True)
            transcript = rewritten
        if transcript:
            print(f"whispr: injecting {len(transcript)} chars", flush=True)
            self.injector.inject(transcript)
        else:
            print("whispr: empty transcript — no injection", flush=True)
            self._emit("no speech detected")

    def _finish(self) -> None:
        """Advance TRANSCRIBING → IDLE once the worker has delivered the Transcript."""
        with self._lock:
            self.state, _ = transition(self.state, Event.COMPLETE)


def _build_from_config(config):
    """Construct the real collaborators from a loaded Config (production wiring)."""
    import subprocess

    from .injector import Injector
    from .recorder import Recorder, make_sounddevice_stream
    from .transcriber import Transcriber

    def notify(message: str) -> None:
        try:
            subprocess.run(["notify-send", "whispr", message], check=False)
        except FileNotFoundError:
            pass

    notifier = notify if config.notify else None
    # Bind the configured capture device into the stream-factory seam.
    recorder = Recorder(
        stream_factory=lambda cb: make_sounddevice_stream(cb, device=config.input_device)
    )
    transcriber = Transcriber(config, notify=notifier)
    injector = Injector()
    rewriter = None
    if config.rewrite:
        from .rewriter import Rewriter, make_openai_completer

        rewriter = Rewriter(
            complete=make_openai_completer(config),
            vocabulary=config.vocabulary,
            log=lambda msg: print(f"whispr: {msg}", flush=True),
        )
    dump_to = (config.cache_dir / "last_recording.wav") if config.dump_last_recording else None
    return recorder, transcriber, injector, rewriter, notifier, dump_to


def run_daemon() -> int:
    """Production entry point: load config, warm the model, serve the socket.

    MVP-0 harness: a blocking accept loop on the main thread (one command at a time),
    with the blocking transcribe + Injection on a worker thread. The GLib main loop
    is deferred to MVP-1 when the tray icon needs it (design decision #6/#14).
    """
    import time

    from .config import load

    config = load()
    print(f"whispr: loading Whisper on device={config.device} …", flush=True)
    t0 = time.monotonic()
    recorder, transcriber, injector, rewriter, notifier, dump_to = _build_from_config(config)
    print(
        f"whispr: model warm on device={transcriber.active_device} "
        f"in {time.monotonic() - t0:.1f}s",
        flush=True,
    )

    daemon = Daemon(
        recorder,
        transcriber,
        injector,
        rewriter=rewriter,
        notify=notifier,
        dump_recording_to=dump_to,
        silence_threshold=config.silence_threshold,
    )

    server = ipc.serve(ipc.DEFAULT_SOCK_PATH)
    print(f"whispr: listening on {ipc.DEFAULT_SOCK_PATH}", flush=True)
    try:
        while True:
            try:
                ipc.handle_once(server, daemon.handle)
            except Exception as exc:  # one bad connection must not kill the Daemon
                print(f"whispr: socket error: {exc}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0
