# Warm daemon, not one-shot scripts

**Decision:** whispr-local runs as a persistent per-user daemon that loads the Whisper model onto the NPU once at startup and stays resident. The GNOME global hotkey invokes a tiny `whispr toggle` client that signals the daemon over a Unix domain socket (`~/.cache/whispr/daemon.sock`); recording and transcription happen inside the warm daemon.

**Why:** Compiling/loading a Whisper model onto the Intel NPU via OpenVINO costs ~5–15s. The reference proof-of-concept used one-shot scripts that paid this cost on *every* dictation, after the user finished speaking — unusable latency for a tool meant to feel instant. A warm daemon pays the model-load cost once, at login. The socket (over a SIGUSR1 signal) gives request/response so `whispr toggle` can report "daemon not running" instead of signalling into the void, and leaves room for `cancel`/`status`/`reload` commands.

**Consequences:** Requires a `systemd --user` service for autostart and lifecycle, plus a GLib main loop in the daemon (which also hosts the future AppIndicator tray icon and the IPC socket). A dead daemon is a new failure mode, surfaced to the user via the `whispr toggle` client's exit code + notification.
