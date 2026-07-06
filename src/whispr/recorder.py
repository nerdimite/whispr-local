"""In-process audio capture into a RAM buffer (no WAV) for whispr.

The Recorder is built behind an injected stream-factory seam so its logic
is testable without touching real audio hardware. The real sounddevice
adapter (`make_sounddevice_stream`) is a thin, un-unit-tested function.
"""

import numpy as np

SAMPLE_RATE = 16000


class Recorder:
    """Captures audio at SAMPLE_RATE mono float32 into an in-memory buffer.

    `device` selects the capture device (None = system default, an int index, or a
    substring of the device name — passed straight to the stream factory). It is a
    plain mutable attribute: `set_device()` swaps it and the next `start()` picks it
    up, so the user can switch mics from the tray between dictations.

    `prepare_device` is an injected seam run at `start()` with the current device. A
    Bluetooth headset only exposes a working mic in its HFP/HSP profile (A2DP, the
    high-quality playback profile, has no mic), so the default implementation flips a
    BT card to a headset profile just for the recording and returns a callable that
    restores the previous profile on `stop()` — keeping music in A2DP while idle.
    """

    def __init__(self, stream_factory=None, reset_backend=None, device=None, prepare_device=None):
        if stream_factory is None:
            stream_factory = make_sounddevice_stream
        self._stream_factory = stream_factory
        # Called to recover a wedged audio backend before one retry (see start()).
        self._reset_backend = reset_backend if reset_backend is not None else reset_audio_backend
        self.device = device
        self._prepare_device = (
            prepare_device if prepare_device is not None else prepare_bluetooth_profile
        )
        self._restore = None
        self._stream = None
        self._chunks = []

    def set_device(self, device):
        """Select the capture device for subsequent recordings (effective on next start)."""
        self.device = device

    def _callback(self, indata, frames, time, status):
        self._chunks.append(np.asarray(indata, dtype=np.float32).copy().reshape(-1))

    def start(self):
        self._chunks = []
        # Switch a Bluetooth headset into its mic-capable profile before capturing.
        # Best-effort: a failure here must not block recording on a normal mic.
        try:
            self._restore = self._prepare_device(self.device)
        except Exception:
            self._restore = None
        try:
            self._stream = self._stream_factory(self._callback, self.device)
            try:
                self._stream.start()
            except Exception:
                # A long-lived daemon can wedge PortAudio into "PortAudio not initialized"
                # (seen under PipeWire). Reset the backend and rebuild the stream once so
                # the user's single toggle still records instead of needing a restart.
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._reset_backend()
                self._stream = self._stream_factory(self._callback, self.device)
                self._stream.start()
        except Exception:
            # Recording never started → undo the profile switch now, since stop()
            # won't be called to do it (the daemon strands nothing in RECORDING).
            self._run_restore()
            raise

    def _run_restore(self):
        """Restore a switched Bluetooth profile, if any. Best-effort, runs once."""
        if self._restore is not None:
            try:
                self._restore()
            except Exception:
                pass
            self._restore = None

    def stop(self) -> np.ndarray:
        try:
            self._stream.close()
        finally:
            self._run_restore()
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks).astype(np.float32)


def normalize_peak(buffer, target_peak=0.95, max_gain=20.0):
    """Scale a float32 capture so its loudest sample reaches ~`target_peak`.

    A Bluetooth headset in HFP mode (and quiet mics generally) produce a low-level
    signal that Whisper transcribes poorly unless you speak right into the mic. This
    lifts a real-but-quiet capture to a level Whisper hears clearly, capping the gain
    (`max_gain`) so near-silence isn't blown up and only ever boosting — never
    attenuating an already-loud capture. Preserves signal-to-noise (a flat gain), so
    a caller's silence gate on the *raw* level still works.
    """
    arr = np.asarray(buffer, dtype=np.float32)
    if arr.size == 0:
        return arr
    peak = float(np.abs(arr).max())
    if peak <= 0.0:
        return arr
    gain = min(target_peak / peak, max_gain)
    if gain <= 1.0:
        return arr
    return np.clip(arr * gain, -1.0, 1.0).astype(np.float32)


def reset_audio_backend():
    """Force-reinitialise PortAudio to clear a wedged 'not initialized' state.

    sounddevice initialises PortAudio once at import; a long-lived daemon can lose
    that (backend restart, PipeWire churn) and every subsequent stream then fails.
    A terminate+initialise pair restores a clean global state. Best-effort and
    sounddevice-specific — a no-op if it isn't the active backend.
    """
    try:
        import sounddevice as sd
    except Exception:
        return
    try:
        sd._terminate()
    except Exception:
        pass
    try:
        sd._initialize()
    except Exception:
        pass


# -- Bluetooth headset profile switching -------------------------------------
# A BT headset can't play A2DP (hi-fi stereo) and capture mic at the same time —
# the mic only exists in the HFP/HSP "headset" profile. So when the user records
# from a `bluez_input.*` source we flip its card into a headset profile for the
# recording, then restore the previous profile. These helpers are split from the
# real PipeWire/wpctl I/O (`_pw_dump`, subprocess) so `bluetooth_card_for` and
# `prepare_bluetooth_profile` are unit-testable with injected fakes.

# Preferred headset profile names, best codec first (mSBC > CVSD).
_HEADSET_PROFILE_PREFS = ("headset-head-unit", "headset-head-unit-cvsd")


def _pw_dump():
    """Return parsed `pw-dump` objects; raises if PipeWire tools aren't present."""
    import json
    import subprocess

    out = subprocess.run(
        ["pw-dump"], capture_output=True, text=True, timeout=5, check=True
    ).stdout
    return json.loads(out)


def bluetooth_card_for(device, objects):
    """Resolve the Bluetooth card behind `device` from `pw-dump` objects.

    Returns {"id", "active", "headset"} — the card's WirePlumber id, its currently
    active profile index, and the best available headset (HFP/HSP) profile index —
    or None if `device` isn't a Bluetooth source or the card has no headset profile.
    """
    if not isinstance(device, str) or not device.startswith("bluez"):
        return None

    card_id = None
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        props = (obj.get("info") or {}).get("props") or {}
        name = props.get("node.name")
        if name and (name == device or device in name):
            card_id = props.get("device.id")
            break
    if card_id is None:
        return None

    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Device" or obj.get("id") != card_id:
            continue
        params = (obj.get("info") or {}).get("params") or {}
        active = None
        for profile in params.get("Profile", []):
            active = profile.get("index")
        available = {}
        for profile in params.get("EnumProfile", []):
            if profile.get("available") != "no":
                available[profile.get("name")] = profile.get("index")
        headset = None
        for pref in _HEADSET_PROFILE_PREFS:
            if pref in available:
                headset = available[pref]
                break
        if headset is None:
            for pname, pidx in available.items():
                if pname and "headset" in pname:
                    headset = pidx
                    break
        if headset is None:
            return None
        return {"id": card_id, "active": active, "headset": headset}
    return None


def prepare_bluetooth_profile(device, dump=None, set_profile=None, sleep=None):
    """Ensure a Bluetooth mic can capture, returning a restore callable (or None).

    If `device` is a `bluez_*` source whose card isn't already in a headset profile,
    switch it and wait for the mic to come up, then return a callable that restores
    the previous profile. Returns None (nothing to restore) for a non-Bluetooth
    device, when PipeWire tools are absent, or when the card is already in a headset
    profile. Best-effort — the recorder swallows any error from here.
    """
    dump = dump or _pw_dump
    set_profile = set_profile or _wpctl_set_profile
    if sleep is None:
        import time

        sleep = time.sleep

    try:
        objects = dump()
    except Exception:
        return None
    info = bluetooth_card_for(device, objects)
    if info is None or info["active"] == info["headset"]:
        return None  # not Bluetooth, or the mic already works in the current profile

    previous = info["active"]
    print(f"whispr: switching Bluetooth headset to mic profile for {device}", flush=True)
    set_profile(info["id"], info["headset"])
    _await_profile(device, info["headset"], dump, sleep)

    def restore():
        if previous is not None:
            print(f"whispr: restoring Bluetooth headset profile for {device}", flush=True)
            set_profile(info["id"], previous)

    return restore


def _await_profile(device, target, dump, sleep, timeout=2.0, interval=0.15):
    """Poll until the card reports `target` as its active profile (bounded), then a
    short settle so the ALSA source node is fully up before we open the stream."""
    waited = 0.0
    while waited < timeout:
        sleep(interval)
        waited += interval
        try:
            info = bluetooth_card_for(device, dump())
        except Exception:
            continue
        if info and info["active"] == target:
            break
    sleep(0.3)


def _wpctl_set_profile(card_id, profile_index):
    """Switch a card's profile via WirePlumber. Best-effort; not unit-tested."""
    import subprocess

    subprocess.run(
        ["wpctl", "set-profile", str(card_id), str(profile_index)],
        check=False,
        timeout=5,
    )


def list_input_devices():
    """Enumerate capture devices for the tray, friendly-first. Not unit-tested.

    Returns a list of {"device", "name", "is_default"} where `name` is a
    human-readable label and `device` is what to hand back to `set_device`
    (sounddevice accepts it as-is: a PipeWire source name substring or an int index).

    Prefers PipeWire's `Audio/Source` nodes (same set GNOME's Sound Input shows —
    real mics with friendly descriptions, no monitor sinks or raw `hw:` ALSA nodes).
    Falls back to a monitor-filtered raw sounddevice list on non-PipeWire systems.
    """
    return _pipewire_input_devices() or _sounddevice_input_devices()


def _pipewire_input_devices():
    """Friendly capture-source list from `pw-dump`; [] if PipeWire isn't available.

    Maps each `Audio/Source` node to its `node.description` (label) + `node.name`
    (the device value, which sounddevice matches as a name substring), and marks the
    node that PipeWire reports as the default source.
    """
    import json
    import subprocess

    try:
        out = subprocess.run(
            ["pw-dump"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
        objects = json.loads(out)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return []

    default_source = None
    for obj in objects:
        if obj.get("type") == "PipeWire:Interface:Metadata":
            for entry in obj.get("metadata", []):
                if entry.get("key") == "default.audio.source":
                    value = entry.get("value")
                    if isinstance(value, dict):
                        default_source = value.get("name")

    devices = []
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        props = (obj.get("info") or {}).get("props") or {}
        if props.get("media.class") != "Audio/Source":
            continue
        name = props.get("node.name")
        if not name:
            continue
        label = props.get("node.description") or props.get("node.nick") or name
        devices.append(
            {"device": name, "name": label, "is_default": name == default_source}
        )
    return devices


def _sounddevice_input_devices():
    """Fallback raw enumeration via sounddevice, with monitor/loopback names filtered."""
    import sounddevice as sd

    try:
        default_input = sd.default.device[0]
    except Exception:
        default_input = None

    devices = []
    for index, info in enumerate(sd.query_devices()):
        name = info.get("name", f"device {index}")
        if info.get("max_input_channels", 0) <= 0 or ".monitor" in name:
            continue
        devices.append(
            {"device": index, "name": name, "is_default": index == default_input}
        )
    return devices


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
