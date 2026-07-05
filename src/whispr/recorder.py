"""In-process audio capture into a RAM buffer (no WAV) for whispr.

The Recorder is built behind an injected stream-factory seam so its logic
is testable without touching real audio hardware. The real sounddevice
adapter (`make_sounddevice_stream`) is a thin, un-unit-tested function.
"""

import numpy as np

SAMPLE_RATE = 16000


class Recorder:
    """Captures audio at SAMPLE_RATE mono float32 into an in-memory buffer."""

    def __init__(self, stream_factory=None):
        if stream_factory is None:
            stream_factory = make_sounddevice_stream
        self._stream_factory = stream_factory
        self._stream = None
        self._chunks = []

    def _callback(self, indata, frames, time, status):
        self._chunks.append(np.asarray(indata, dtype=np.float32).copy().reshape(-1))

    def start(self):
        self._chunks = []
        self._stream = self._stream_factory(self._callback)
        self._stream.start()

    def stop(self) -> np.ndarray:
        self._stream.close()
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks).astype(np.float32)


def make_sounddevice_stream(callback, device=None):
    """Real stream factory backed by sounddevice. Not exercised in unit tests.

    `device` is passed to sounddevice: None = system default, an int index, or a
    substring of the device name. The Daemon binds it from `config.input_device`.
    """
    import sounddevice as sd

    return sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=callback,
        device=device,
    )
