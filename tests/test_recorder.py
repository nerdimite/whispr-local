import numpy as np

from whispr.recorder import (
    Recorder,
    bluetooth_card_for,
    normalize_peak,
    prepare_bluetooth_profile,
)


def _noop(_device):
    """Default prepare_device seam for tests — no Bluetooth profile switching."""
    return None


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


def make_fake_factory(frames_batches, seen_devices=None):
    def factory(callback, device=None):
        if seen_devices is not None:
            seen_devices.append(device)
        return FakeStream(callback, frames_batches)

    return factory


def test_start_stop_returns_mono_f32_buffer():
    chunk1 = np.array([[0.1], [0.2], [0.3], [0.4]], dtype=np.float32)
    chunk2 = np.array([[0.5], [0.6], [0.7], [0.8]], dtype=np.float32)
    factory = make_fake_factory([chunk1, chunk2])

    recorder = Recorder(stream_factory=factory, prepare_device=_noop)
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

    recorder = Recorder(stream_factory=factory, prepare_device=_noop)
    recorder.start()
    result = recorder.stop()

    assert isinstance(result, np.ndarray)
    assert result.ndim == 1
    assert result.dtype == np.float32
    assert len(result) == 0


def test_start_recovers_when_portaudio_wedges():
    # A long-lived daemon can wedge PortAudio into "not initialized"; the first
    # stream.start() then throws. The Recorder should reset the audio backend and
    # rebuild the stream once, so the user's single press still records.
    attempts = {"n": 0}
    resets = {"n": 0}

    def factory(callback, device=None):
        attempts["n"] += 1
        fail = attempts["n"] == 1  # first build's start() wedges, second is clean
        return WedgingStream(callback, fail=fail)

    recorder = Recorder(stream_factory=factory, reset_backend=lambda: resets.__setitem__("n", resets["n"] + 1), prepare_device=_noop)
    recorder.start()

    assert attempts["n"] == 2  # rebuilt once
    assert resets["n"] == 1  # backend reset before the retry
    assert recorder._stream.started is True


def test_device_is_passed_to_the_stream_factory():
    seen = []
    recorder = Recorder(stream_factory=make_fake_factory([], seen_devices=seen), device=3, prepare_device=_noop)
    recorder.start()
    recorder.stop()
    assert seen == [3]


def test_set_device_takes_effect_on_next_start():
    seen = []
    recorder = Recorder(stream_factory=make_fake_factory([], seen_devices=seen), prepare_device=_noop)
    recorder.start()  # default device (None)
    recorder.stop()
    recorder.set_device("USB mic")
    recorder.start()  # switched device
    recorder.stop()
    assert seen == [None, "USB mic"]


def test_start_does_not_reset_backend_on_success():
    resets = {"n": 0}
    factory = make_fake_factory([])
    recorder = Recorder(stream_factory=factory, reset_backend=lambda: resets.__setitem__("n", resets["n"] + 1), prepare_device=_noop)
    recorder.start()
    assert resets["n"] == 0  # healthy path never touches the backend


def test_normalize_peak_boosts_quiet_capture_to_target():
    quiet = np.full(100, 0.1, dtype=np.float32)
    out = normalize_peak(quiet, target_peak=0.95, max_gain=20.0)
    assert abs(float(np.abs(out).max()) - 0.95) < 1e-4  # lifted to target


def test_normalize_peak_caps_gain_on_near_silence():
    tiny = np.full(100, 0.001, dtype=np.float32)
    out = normalize_peak(tiny, target_peak=0.95, max_gain=20.0)
    # gain capped at 20x, not the ~950x needed to hit target
    assert abs(float(np.abs(out).max()) - 0.02) < 1e-4


def test_normalize_peak_never_attenuates_loud_capture():
    loud = np.array([0.0, 0.99, -0.8], dtype=np.float32)
    out = normalize_peak(loud)
    np.testing.assert_array_equal(out, loud)  # already loud → unchanged


def test_normalize_peak_leaves_empty_and_silent_untouched():
    assert normalize_peak(np.zeros(0, dtype=np.float32)).size == 0
    silent = np.zeros(10, dtype=np.float32)
    np.testing.assert_array_equal(normalize_peak(silent), silent)


def test_prepare_device_switches_then_restores_around_capture():
    events = []

    def prepare(device):
        events.append(("prepare", device))
        return lambda: events.append(("restore", device))

    recorder = Recorder(stream_factory=make_fake_factory([]), device="bluez_input.x", prepare_device=prepare)
    recorder.start()
    assert events == [("prepare", "bluez_input.x")]  # switched, not yet restored
    recorder.stop()
    assert events == [("prepare", "bluez_input.x"), ("restore", "bluez_input.x")]


def test_prepare_device_none_means_no_restore():
    # A non-Bluetooth device: prepare returns None → stop() must not blow up.
    recorder = Recorder(stream_factory=make_fake_factory([]), prepare_device=lambda d: None)
    recorder.start()
    recorder.stop()  # no restore callable; should be a clean no-op


def test_restore_runs_when_stream_start_fails():
    # If the stream never starts, the profile switch must still be undone (stop()
    # is not called by the daemon on a failed start).
    restored = []

    def prepare(device):
        return lambda: restored.append(device)

    def factory(callback, device=None):
        return WedgingStream(callback, fail=True)  # both attempts fail

    recorder = Recorder(
        stream_factory=factory, reset_backend=lambda: None, device="bluez_input.x", prepare_device=prepare
    )
    try:
        recorder.start()
    except RuntimeError:
        pass
    assert restored == ["bluez_input.x"]


# -- Bluetooth profile resolution (pure, over fake pw-dump objects) ----------

def _bt_objects(active_profile):
    """A minimal pw-dump-shaped fixture: one bluez source node + its card."""
    return [
        {
            "type": "PipeWire:Interface:Node",
            "info": {"props": {"node.name": "bluez_input.AA", "media.class": "Audio/Source", "device.id": 42}},
        },
        {
            "type": "PipeWire:Interface:Device",
            "id": 42,
            "info": {
                "params": {
                    "Profile": [{"index": active_profile, "name": "active"}],
                    "EnumProfile": [
                        {"index": 100, "name": "a2dp-sink", "available": "yes"},
                        {"index": 200, "name": "headset-head-unit", "available": "yes"},
                        {"index": 199, "name": "headset-head-unit-cvsd", "available": "yes"},
                    ],
                }
            },
        },
    ]


def test_bluetooth_card_for_finds_card_and_prefers_msbc():
    info = bluetooth_card_for("bluez_input.AA", _bt_objects(active_profile=100))
    assert info == {"id": 42, "active": 100, "headset": 200}  # 200 = mSBC, preferred


def test_bluetooth_card_for_ignores_non_bluetooth():
    assert bluetooth_card_for(3, _bt_objects(active_profile=100)) is None
    assert bluetooth_card_for("alsa_input.builtin", _bt_objects(active_profile=100)) is None


def test_prepare_switches_when_in_a2dp():
    calls = []
    restore = prepare_bluetooth_profile(
        "bluez_input.AA",
        dump=lambda: _bt_objects(active_profile=100),
        set_profile=lambda cid, idx: calls.append((cid, idx)),
        sleep=lambda _s: None,
    )
    assert calls == [(42, 200)]  # switched into the headset profile
    restore()
    assert calls == [(42, 200), (42, 100)]  # and restored to the previous profile


def test_prepare_is_noop_when_already_headset():
    calls = []
    restore = prepare_bluetooth_profile(
        "bluez_input.AA",
        dump=lambda: _bt_objects(active_profile=200),  # already in headset profile
        set_profile=lambda cid, idx: calls.append((cid, idx)),
        sleep=lambda _s: None,
    )
    assert restore is None
    assert calls == []


def test_prepare_returns_none_when_pipewire_absent():
    def boom():
        raise FileNotFoundError("pw-dump")

    assert prepare_bluetooth_profile("bluez_input.AA", dump=boom, set_profile=lambda *a: None) is None


class WedgingStream:
    def __init__(self, callback, fail):
        self._callback = callback
        self._fail = fail
        self.started = False
        self.closed = False

    def start(self):
        if self._fail:
            raise RuntimeError("Error starting stream: PortAudio not initialized [PaErrorCode -10000]")
        self.started = True

    def close(self):
        self.closed = True
