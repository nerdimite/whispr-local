# whispr-local

On-device Whisper dictation for Ubuntu GNOME/Wayland. Press **`Super+\`**, speak, press again
— the transcript is pasted into the focused window. Runs locally (no cloud) on the Intel
Lunar Lake **NPU** (~0.1 s per short utterance, ~4× faster than CPU), falling back to CPU
automatically if the NPU is unavailable.

> Design & decisions: `docs/design/v1_design.md`, `docs/adr/`, `CONTEXT.md`.

---

## TL;DR — daily use

The daemon autostarts at login. After a **reboot, just log in and press `Super+\`.** Nothing to start.

```bash
Super+\          # start recording · press again to stop → transcribe → paste
```

Check it's alive:

```bash
~/Projects/whispr-local/.venv/bin/whispr status      # → state=IDLE device=NPU
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

**Status-bar icon:** a microphone icon sits in the GNOME top bar (idle → recording → transcribing).
Click it for a menu: **Start/stop dictation**, **Cancel recording**, **Quit**. It's a separate process
(`whispr-indicator.service`) that polls the daemon, so it never blocks dictation.

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
| `device=CPU` when you wanted NPU | The daemon validates the NPU at startup and falls back if it can't decode. Check `journalctl --user -u whispr` for the reason; confirm the driver with `ls /dev/accel/accel0`. Re-export the model with `scripts/export-model.sh` if it predates the 2025.3 pins. |
| Says "daemon not running" | `systemctl --user restart whispr` and check `journalctl --user -u whispr -n 30`. |

---

## Status & known limitations

- **Runs on the NPU.** Inference is ~0.1 s per short utterance on the Lunar Lake NPU (vs ~0.6 s on
  CPU). The daemon runs a throwaway decode at startup to prove the NPU can actually infer; if it
  can't, it falls back to CPU and notifies. `whispr status` reports the live device.
- **The NPU path is version-locked to OpenVINO 2025.3.** OpenVINO 2026.0 removed the Whisper
  "decoder-with-past" path that runs on the NPU, so 2026.x compiles but throws at `generate()`.
  The export is equally sensitive: `transformers >= 4.53` emit a causal-mask form the NPU static
  pipeline can't consume. `scripts/export-model.sh` therefore pins its own ephemeral export stack
  (`transformers==4.52.4`, `--disable-stateful`) and the runtime pins `openvino*==2025.3`. **Do not
  bump these without re-testing NPU `generate()`.**
- **Lean runtime.** Inference reads the OpenVINO IR directly — the `.venv` carries only the three
  `openvino*` wheels, no torch/transformers/optimum. The heavy export stack lives only in the
  throwaway venv `export-model.sh` builds.
- **Accuracy:** `whisper-base` is the default; `whisper-small` is noticeably sharper and still
  only ~0.3 s/utterance on the NPU. Export it with `scripts/export-model.sh openai/whisper-small`
  and set `model_path` to `~/.local/share/whispr/models/whisper-small` (first NPU compile of the
  bigger model takes ~30 s, then it's cached).
- **Status-bar indicator** runs as a separate process under system `python3` (needs `python3-gi` +
  `gir1.2-ayatanaappindicator3-0.1` and the *Ubuntu AppIndicators* GNOME extension, both default on
  Ubuntu). The lean inference venv has no `gi`, so the indicator is deliberately decoupled and polls
  the daemon over the socket rather than living inside it.

---

## Development

```bash
uv sync          # pure-core + seam tests need only numpy/sounddevice
uv run pytest    # 39 tests: ipc, state, config, recorder, transcriber, injector, daemon
```

The NPU/OpenVINO stack is the optional `npu` extra (`uv sync --extra npu`) with lazy imports, so
the suite runs without it. Hardware/shell modules (recorder/transcriber/injector) sit behind
injected seams and are tested with fakes; the daemon lifecycle is driven directly, no GLib/hardware.
