# whispr-local v1 — PRD

## Problem Statement

I dictate a lot and want the Wispr Flow workflow — press a hotkey, speak, and have the text land in whatever window I'm typing in — but Wispr Flow has no Linux build. I'm on an ASUS ZenBook S14 (Intel Core Ultra 7 256V, Lunar Lake) running Ubuntu on GNOME/Wayland, with a 48-TOPS NPU sitting idle. I want that dictation workflow running **entirely on-device** on the NPU: no cloud, no subscription, no data leaving the laptop. A rough pip-based proof of concept confirmed the transcription pipeline is sound, but it was written for X11 (`xdotool`/`xclip`), reloaded the model from scratch on every use (unusable latency), and was a pile of loose scripts with hardcoded paths.

## Solution

**whispr-local** is a small, personal, on-device dictation tool for GNOME/Wayland. A resident **Daemon** loads a Whisper model onto the NPU once at login and stays warm. Pressing `Super+\` starts a **Recording**; pressing it again stops it, transcribes the speech on the NPU, and **Injects** the resulting **Transcript** into the focused window via clipboard-then-paste. The Transcript stays on the clipboard so a mis-aimed paste is recoverable. If the NPU is unavailable it falls back to CPU automatically and keeps working. Setup (system dependencies, input permissions, the systemd service, the GNOME hotkey, and model export) is handled by a script, not by hand.

Vocabulary follows `CONTEXT.md`: **Dictation**, **Toggle**, **Transcript**, **Injection**, **Daemon**, **State**. Architecture follows ADR-0001 (warm daemon) and ADR-0002 (Wayland injection via ydotool).

## User Stories

1. As a dictating user, I want to press a global hotkey and start speaking, so that I can capture text without switching windows or clicking anything.
2. As a dictating user, I want to press the same hotkey again to stop, so that toggling is a single muscle-memory gesture.
3. As a dictating user, I want the transcribed text pasted into whatever window has focus, so that dictation works in any app — editor, browser field, chat box.
4. As a dictating user, I want transcription to feel near-instant after I stop speaking, so that the tool doesn't interrupt my flow.
5. As a privacy-conscious user, I want everything to run on-device on the NPU, so that no audio or text ever leaves my laptop.
6. As a user who mis-clicks, I want the Transcript to stay on the clipboard after pasting, so that if the wrong window was focused I can click the right spot and paste again.
7. As a user, I want a notification when recording starts, so that I know the microphone is live.
8. As a user, I want a notification while transcribing and when done, so that I'm not left wondering whether it worked.
9. As a user, I want an audible/visible signal when no speech was detected, so that I don't paste an empty string and wonder why nothing happened.
10. As a user on a machine whose NPU driver is too old, I want to be warned during setup, so that I don't silently get garbage transcriptions.
11. As a user whose NPU fails to initialize, I want the tool to fall back to CPU and tell me, so that dictation keeps working even if degraded.
12. As a user, I want to force CPU mode via config, so that I can sidestep the NPU entirely if it ever misbehaves.
13. As a user, I want the Daemon to start automatically at login, so that dictation is always ready without me starting anything.
14. As a user, I want the Daemon to keep the model warm, so that I pay the model-load cost once at login rather than on every Dictation.
15. As a user, I want `whispr toggle` to tell me when the Daemon isn't running, so that I'm not pressing the hotkey into the void.
16. As a user, I want to check the Daemon's current State and active device (NPU/CPU), so that I can confirm it's healthy and know which processor it's using.
17. As a user, I want a pressed hotkey during transcription to be safely rejected (not queued), so that the State stays predictable and I don't trigger surprise recordings.
18. As a user, I want to cancel an in-progress Recording without transcribing, so that I can abort a mistaken start.
19. As a user, I want a single setup script to install system dependencies, so that I don't hand-assemble the environment.
20. As a user, I want the setup script to configure input permissions (uinput/ydotool) and tell me when a re-login is required, so that paste injection works without me debugging permissions.
21. As a user, I want the setup script to bind `Super+\` to `whispr toggle` via gsettings, so that I never touch GNOME Settings by hand.
22. As a user, I want the setup script to offer to export the Whisper model if none is present, so that first-run setup is one command.
23. As a user, I want my configuration (device, model path, cache dir, notifications) in a TOML file under `~/.config`, so that I can tweak behavior without editing code.
24. As a user, I want models stored outside the repo in an XDG data directory, so that large binaries don't pollute the project or git.
25. As a user, I want the NPU compile cached, so that Daemon restarts are fast, not just the first-ever load.
26. As a developer, I want the Daemon logs to state which device won and the model-load time, so that I can verify the NPU path is actually being used.
27. As a developer, I want the record→transcribe→inject lifecycle to run without blocking the IPC socket, so that the Daemon stays responsive during transcription.
28. As a developer, I want the pure logic (config, state machine, IPC framing) unit-tested, so that I have a regression net around the parts most likely to break silently.
29. As a user (fast-follow, MVP-1), I want a tray icon that reflects idle/recording/transcribing/error State, so that I always know what the Daemon is doing at a glance.

## Implementation Decisions

**Architecture — warm Daemon (ADR-0001).** A persistent per-user process runs a GLib main loop. The GNOME `Super+\` shortcut invokes `whispr toggle`, which signals the Daemon over a **Unix domain socket** at `~/.cache/whispr/daemon.sock`. The Daemon loads the OpenVINO `WhisperPipeline` once at startup and holds it warm. Autostart and lifecycle via a `systemd --user` service.

**Injection — Wayland-native (ADR-0002).** Transcript delivery is `wl-copy` (write clipboard) + `ydotool key ctrl+v` (simulate paste). `xdotool`/`xclip` are rejected (X11-only); `wtype` is rejected (GNOME/Mutter refuses its protocol). The clipboard is **not** restored. `ydotool` requires a `ydotoold --user` service and `/dev/uinput` access via a udev rule + `input` group membership.

**Modules** (deep modules with narrow interfaces called out):

- **`config`** — loads/validates `~/.config/whispr/config.toml`, expands paths, supplies defaults. Pure, no I/O beyond the file read. Fields: `device` (`"NPU"` default w/ auto-fallback, or `"CPU"`), `model_path`, `cache_dir`, `dump_last_recording` (bool, default false), `notify` (bool, default true).
- **`state`** — the State machine as pure logic: given current State + a Toggle/cancel/complete event, returns the next State and the side-effect to perform. Reject-while-TRANSCRIBING lives here. From a prototype-level sketch, the transitions are:

  ```
  IDLE        + toggle    -> RECORDING     (start stream)
  RECORDING   + toggle    -> TRANSCRIBING  (stop stream, dispatch buffer to worker)
  RECORDING   + cancel    -> IDLE          (discard buffer)
  TRANSCRIBING+ toggle    -> TRANSCRIBING  (reject: notify "busy")
  TRANSCRIBING+ complete  -> IDLE          (inject transcript, or notify "no speech")
  ```

- **`ipc`** — Unix socket server (in Daemon) + client (in `whispr toggle`/`status`/`cancel`), plus the command/reply framing. Framing is pure and testable without a live socket. Client reports a clean error when the Daemon is absent.
- **`transcriber`** — wraps `WhisperPipeline`; selects device once at startup, catches NPU init failure and falls back to CPU (sticky for the Daemon's life), sets OpenVINO `CACHE_DIR`. Fallback branch is testable via an injected fake pipeline.
- **`recorder`** — opens a `sounddevice` InputStream at **16 kHz mono float32**, accumulates frames into a numpy buffer on the PortAudio callback thread; on stop, concatenates and returns the buffer. No WAV file (optional debug dump when `dump_last_recording`).
- **`injector`** — thin shell-out to `wl-copy` and `ydotool`.
- **`daemon`** — wires GLib loop + socket + State machine + a **worker thread** for the blocking `WhisperPipeline.generate()` and Injection, so the main loop never blocks.

**CLI** — single `whispr` entry point: `daemon` (run resident, systemd-managed), `toggle` (the hotkey target), `status` (print State + active device), `cancel` (drop in-progress Recording).

**NPU/CPU fallback** — device decided **once at startup**, sticky, `notify-send` on fallback, non-fatal. Setup script warns if NPU driver `< 32.0.100.3104` (the silent-garbage threshold) since that failure mode can't be caught at runtime.

**Setup** — `scripts/setup-system.sh`: APT deps (`libportaudio2`, `wl-clipboard`, `ydotool`, `libnotify-bin`, AppIndicator libs for MVP-1); uinput udev rule + `input` group + `ydotoold --user` service (warns re-login needed); NPU driver version check; install + enable the `whispr` systemd `--user` service; bind `Super+\` via `gsettings`; offer to run `scripts/export-model.sh` if no model present. `export-model.sh` runs `optimum-cli export openvino … whisper-base … --weight-format int8` into `~/.local/share/whispr/models/`.

**Environment** — uv-managed project, **Python 3.12** pinned, `src/whispr/` layout, one console-script entry point, locked deps (the NPU-sensitive pins: `openvino*`/`optimum-intel`/`transformers`/`nncf`/`onnx` per reference).

## Testing Decisions

**What makes a good test here:** it exercises a module's external behavior through its public interface, not its internals. For the State machine, that means asserting "given State X and event Y, the next State and emitted side-effect are Z" — never poking at private attributes. For `config`, "given this TOML (or a missing/partial one), these resolved values come out." For `ipc`, "this command round-trips through encode→decode unchanged" and "the client reports daemon-absent cleanly." Tests must not require the NPU, a microphone, a Wayland session, or `ydotool`.

**Modules under test (per developer decision): the pure core.**

- **`config`** — defaults applied, path expansion, TOML parse, invalid/missing-file handling, `device` normalization.
- **`state`** — every transition in the table above, especially reject-while-TRANSCRIBING and cancel-from-RECORDING; assert emitted side-effects, not just resulting State.
- **`ipc`** — command/reply framing round-trips; malformed input handled; client surfaces a clean error when the socket is absent.

`transcriber` fallback, `recorder`, and `injector` are **not** unit-tested in v1 — the fallback branch is covered manually by the CPU-forced acceptance run; the hardware/shell-out wrappers are proven by the MVP-0 end-to-end run. There is no existing test suite to mirror; this establishes the pattern (pytest, pure functions, dependency injection for the one fake pipeline should transcriber tests ever be added).

**MVP-0 acceptance (end-to-end, manual):** `whispr daemon` logs the winning device + load time; `Super+\` → speak → `Super+\` puts text into a focused editor **and** a browser field; Transcript survives on the clipboard for manual re-paste; forcing `device = "CPU"` and restarting still works.

## Out of Scope

- **Tray icon** — deferred to MVP-1 (fast-follow), not the first tested milestone. States: idle/recording/transcribing/error.
- **LLM cleanup pass** over the raw Transcript (Wispr-Flow-style) — explicitly a later, separate task.
- **X11 support** — target is GNOME/Wayland only.
- **GUI / settings window** — config is a hand-edited TOML file.
- **Push-to-talk (hold)** — v1 is two-press Toggle only.
- **Multiple concurrent Dictations / queuing** — one at a time, reject-while-busy.
- **Model management UI, model switching at runtime** — model chosen via config + export script (`whisper-base` default, `whisper-small` a manual swap).
- **Packaging/distribution** (deb, Flatpak, PyPI) — personal tool, run from the repo via uv.
- **Non-Ubuntu GNOME** — assumes Ubuntu's default AppIndicator extension for MVP-1.

## Further Notes

- The reference proof-of-concept (`docs/reference/`) is **untested throwaway** — it validated the OpenVINO NPU transcription approach and nothing else. Do not port its X11 injection, its one-shot process model, or its hardcoded paths.
- Biggest deltas from the reference: (1) X11 → Wayland forces `ydotool`/uinput instead of `xdotool`; (2) NPU model-load cost forces a warm Daemon instead of one-shot scripts; (3) in-process `sounddevice` replaces the `arecord` subprocess + WAV round-trip.
- Direction of travel: once v1 is solid, layer a small local LLM (or Gemma 4 once NPU support lands in OpenVINO) as a cleanup pass over the raw Transcript before Injection.
