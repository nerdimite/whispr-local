# Injection via wl-copy + ydotool (uinput), not xdotool/xclip

**Decision:** The Transcript is delivered to the focused window by writing it to the clipboard with `wl-copy` (wl-clipboard) and simulating Ctrl+V with `ydotool key ctrl+v`. The clipboard is deliberately *not* restored afterwards. `ydotool` requires a `ydotoold` user service and `/dev/uinput` access, set up via a udev rule + `input` group membership in `scripts/setup-system.sh`.

**Why:** The target environment is GNOME on **Wayland**, where the reference's `xdotool`/`xclip` (X11-only) cannot inject input or read/write another app's clipboard. `wtype` is a Wayland-native alternative but GNOME/Mutter refuses the virtual-keyboard protocol it needs, so it doesn't work here. `ydotool` operates below the display server via the kernel's `/dev/uinput`, which is the only reliable auto-paste path on GNOME Wayland. Clipboard-then-paste (over `ydotool type`) preserves unicode/punctuation fidelity. Leaving the Transcript on the clipboard lets the user re-paste manually if the wrong window was focused.

**Consequences:** Adds one-time privileged setup (udev rule, group change requiring re-login, a `ydotoold --user` service). Dictation overwrites the clipboard by design. On a non-Ubuntu GNOME the tray icon (ADR forthcoming/MVP-1) would additionally need the AppIndicator extension, which Ubuntu ships by default.
