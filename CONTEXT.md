# whispr-local

A local, on-device dictation tool for Ubuntu (GNOME/Wayland): press a global hotkey, speak, press again, and the transcribed text is pasted into the focused window. Runs entirely on the Intel Lunar Lake NPU via OpenVINO Whisper. No cloud.

## Language

**Dictation**:
One full cycle: hotkey-start → record speech → hotkey-stop → transcribe → paste. The unit of user interaction.

**Toggle**:
A single press of the global hotkey. The first Toggle starts recording; the second stops it and triggers transcription.
_Avoid_: "hotkey event", "trigger"

**Transcript**:
The text Whisper produces from one recording. Written to the clipboard and pasted into the focused window; left on the clipboard afterwards for manual re-paste.

**Injection**:
The act of getting the Transcript into the focused window: `wl-copy` writes it to the Wayland clipboard, then `ydotool` simulates Ctrl+V.
_Avoid_: "paste" (ambiguous — could mean the manual re-paste), "type"

**Daemon**:
The resident per-user process. Loads the Whisper model onto the NPU once at startup, holds it warm, and owns the record→transcribe→inject lifecycle. Runs a GLib main loop hosting the IPC socket (and, later, the tray icon).

**State**:
The Daemon is always in exactly one of three: **IDLE** (ready), **RECORDING** (capturing audio), **TRANSCRIBING** (running Whisper + injecting). A Toggle received while TRANSCRIBING is rejected, not queued.

## Relationships

- A **Dictation** is bounded by two **Toggles**
- A **Dictation** produces one **Transcript**
- A **Transcript** is delivered by one **Injection**
- The **Daemon** processes one **Dictation** at a time; its **State** advances IDLE → RECORDING → TRANSCRIBING → IDLE

## Flagged ambiguities

- "paste" was used for both the automated Ctrl+V simulation and the user's manual re-paste — resolved: the automated step is **Injection**; "paste" refers only to the manual re-paste the user can do because the Transcript stays on the clipboard.
