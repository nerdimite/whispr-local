import numpy as np

from whispr.recorder import Recorder


class FakeStream:
    def __init__(self, callback, frames_batches):
        self._callback = callback
        self._frames_batches = frames_batches
        self.started = False
        self.closed = False

    def start(self):
        self.started = True
        for batch in self._frames_batches:
            self._callback(batch, batch.shape[0], None, None)

    def close(self):
        self.closed = True


def make_fake_factory(frames_batches):
    def factory(callback):
        return FakeStream(callback, frames_batches)

    return factory


def test_start_stop_returns_mono_f32_buffer():
    chunk1 = np.array([[0.1], [0.2], [0.3], [0.4]], dtype=np.float32)
    chunk2 = np.array([[0.5], [0.6], [0.7], [0.8]], dtype=np.float32)
    factory = make_fake_factory([chunk1, chunk2])

    recorder = Recorder(stream_factory=factory)
    recorder.start()
    result = recorder.stop()

    expected = np.concatenate([chunk1.reshape(-1), chunk2.reshape(-1)])

    assert isinstance(result, np.ndarray)
    assert result.ndim == 1
    assert result.dtype == np.float32
    assert len(result) == 8
    np.testing.assert_array_equal(result, expected)


def test_stop_with_no_frames_returns_empty():
    factory = make_fake_factory([])

    recorder = Recorder(stream_factory=factory)
    recorder.start()
    result = recorder.stop()

    assert isinstance(result, np.ndarray)
    assert result.ndim == 1
    assert result.dtype == np.float32
    assert len(result) == 0
