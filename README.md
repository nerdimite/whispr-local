# whispr-local

On-device Whisper dictation for Ubuntu GNOME/Wayland. Press **`Super+\`**, speak, press again
— the transcript is pasted into the focused window. Runs locally (no cloud) on the Intel
Lunar Lake NPU, falling back to CPU automatically.

> Design & decisions: `docs/design/v1_design.md`, `docs/adr/`, `CONTEXT.md`.

---

## TL;DR — daily use

The daemon autostarts at login. After a **reboot, just log in and press `Super+\`.** Nothing to start.

```bash
Super+\          # start recording · press again to stop → transcribe → paste
```

Check it's alive:

```bash
~/Projects/whispr-local/.venv/bin/whispr status      # → state=IDLE device=CPU
```

(Optional: `alias whispr="$HOME/Projects/whispr-local/.venv/bin/whispr"` in your `~/.bashrc`.)

---

## First-time setup

Two phases, split around a **re-login** (group changes need it).

**1. System setup (sudo):**

```bash
cd ~/Projects/whispr-local
bash scripts/setup-system.sh
```

Installs APT deps, `/dev/uinput` udev rule, `input`+`render` groups, the **Intel NPU driver**,
the Python env (`uv sync --extra npu`), and offers to export the Whisper model.

**2. Log out and back in.**

**3. User setup (no sudo):**

```bash
bash scripts/setup-user.sh
```

Enables the `ydotoold` + `whispr` services, binds `Super+\`, and verifies the mic + device.

Then do the first dictation into any text field.

---

## Everyday commands

| Command | What it does |
|---|---|
| `Super+\` | Toggle a dictation (record ⇄ stop+transcribe+paste) |
| `whispr status` | Show state + active device (NPU/CPU) |
| `whispr toggle` | Same as the hotkey (start/stop) |
| `whispr cancel` | Drop an in-progress recording without transcribing |
| `journalctl --user -u whispr -f` | Watch the daemon live (device, rms, transcript, paste) |
| `systemctl --user restart whispr` | Restart the daemon (after a config change) |

**Clipboard note:** the transcript stays on the clipboard after pasting, so if the wrong window
was focused you can just `Ctrl+V` again where you meant to.

---

## Configuration

Edit `~/.config/whispr/config.toml` (all fields optional — see `config.example.toml`), then
`systemctl --user restart whispr`.

| Field | Default | Purpose |
|---|---|---|
| `device` | `"NPU"` | `"NPU"` (auto-falls-back to CPU) or `"CPU"` |
| `input_device` | system default | Mic to record from — an index or a name substring. **Pin this** if bluetooth keeps stealing the mic. |
| `silence_threshold` | `0.02` | Skip transcription below this RMS (stops Whisper hallucinating on silence). Tune from the logged `rms=`. |
| `notify` | `true` | Desktop notifications |
| `dump_last_recording` | `false` | Write the last capture to `<cache_dir>/last_recording.wav` for debugging |

This machine is pinned to the internal mic (`input_device = "HiFi__Mic__source"`) so the JBL
headset can't feed it silence.

---

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| Notification appears but **nothing pastes** | `ydotoold` down or missing `input` group. `systemctl --user status ydotoold`; re-login if just added to `input`. |
| Pastes an empty/phantom word ("you") | Captured silence (Whisper hallucinates). Check `journalctl` `rms=` — raise/lower `silence_threshold`. |
| **Records silence** (`rms=0.000`) | Wrong mic (often a bluetooth headset default). Pin `input_device` to your real mic; list options: `.venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"`. |
| `device=CPU` when you wanted NPU | Known: NPU Whisper inference is broken on the current OpenVINO pins (see below). CPU is used automatically. |
| Says "daemon not running" | `systemctl --user restart whispr` and check `journalctl --user -u whispr -n 30`. |

---

## Status & known limitations

- **Runs on CPU today.** The NPU driver installs and the model compiles on the NPU, but
  `WhisperPipeline.generate()` fails on the NPU with the current `openvino-genai` / `optimum-intel`
  pins (a version-matrix issue, not our code). The daemon validates the NPU at startup and cleanly
  falls back to CPU. `device` stays `NPU` so it'll use the NPU automatically once the pins are fixed.
- **Accuracy** is `whisper-base`. For sharper transcripts, re-export `whisper-small`
  (`scripts/export-model.sh openai/whisper-small`) and point `model_path` at it.
- **No tray icon yet** — MVP-1 (needs the GLib loop the daemon currently omits).

---

## Development

```bash
uv sync          # pure-core + seam tests need only numpy/sounddevice
uv run pytest    # 39 tests: ipc, state, config, recorder, transcriber, injector, daemon
```

The NPU/OpenVINO stack is the optional `npu` extra (`uv sync --extra npu`) with lazy imports, so
the suite runs without it. Hardware/shell modules (recorder/transcriber/injector) sit behind
injected seams and are tested with fakes; the daemon lifecycle is driven directly, no GLib/hardware.
