import subprocess
import time

# Ctrl+V as raw Linux input keycodes, which is what `ydotool key` expects (it does
# NOT understand xdotool-style "ctrl+v" — non-interpretable tokens are silently
# treated as delays and paste nothing). 29 = KEY_LEFTCTRL, 47 = KEY_V; `:1` = press,
# `:0` = release. Order: ctrl down, v down, v up, ctrl up.
PASTE_KEYCODES = ["29:1", "47:1", "47:0", "29:0"]


class Injector:
    """Injects a transcript into the focused window via clipboard + paste.

    Order matters (ADR-0002): write the text to the Wayland clipboard with
    wl-copy, THEN simulate a paste with ydotool. The clipboard is not
    restored afterwards. Empty text is a no-op.
    """

    def __init__(self, run=subprocess.run, settle: float = 0.05):
        self.run = run
        self.settle = settle

    def inject(self, text: str) -> None:
        if not text:
            return

        self.run(["wl-copy"], input=text, text=True, check=False)

        # Small settle so the clipboard is served before we paste (wl-copy forks a
        # background server; pasting too eagerly can race it). Tunable via config.
        if self.settle > 0:
            time.sleep(self.settle)

        self.run(["ydotool", "key", *PASTE_KEYCODES], check=False)
