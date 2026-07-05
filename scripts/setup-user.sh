#!/usr/bin/env bash
# whispr-local setup — PHASE 2 (per-user, no sudo). Run this AFTER re-login.
#
# Enables the user services (which need the input/render groups now active), binds
# the Super+W hotkey, and verifies the NPU is visible to OpenVINO. Safe to re-run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
MODEL_DIR="$DATA_HOME/whispr/models/whisper-base"
UV_BIN="$(command -v uv || true)"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*"; }

if [[ -z "$UV_BIN" ]]; then
  warn "uv not found on PATH — run phase 1 (scripts/setup-system.sh) first."; exit 1
fi

# --- 0. Preconditions -----------------------------------------------------
for grp in input render; do
  if ! id -nG | tr ' ' '\n' | grep -qx "$grp"; then
    warn "You are not in the '$grp' group yet. Did you log out and back in after phase 1?"
    warn "Without it, $([[ $grp == input ]] && echo 'ydotool paste' || echo 'NPU access') will fail."
  fi
done
if [[ ! -f "$MODEL_DIR/openvino_encoder_model.xml" ]]; then
  warn "No model at $MODEL_DIR — run scripts/export-model.sh before first use."
fi

# --- 1. ydotoold user service ---------------------------------------------
say "Enabling ydotoold --user service (uinput backend for paste)"
mkdir -p "$CONFIG_HOME/systemd/user"
cat > "$CONFIG_HOME/systemd/user/ydotoold.service" <<'UNIT'
[Unit]
Description=ydotoold (virtual input backend for whispr)
[Service]
# Clear a socket left behind by an unclean exit so a fresh start doesn't hit
# "Another ydotoold is running with the same socket." (%t = /run/user/<uid>)
ExecStartPre=-/usr/bin/rm -f %t/.ydotool_socket
ExecStart=/usr/bin/ydotoold
Restart=on-failure
RestartSec=1
[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
# Stop + reset any orphaned/failed instance before starting cleanly.
systemctl --user stop ydotoold.service 2>/dev/null || true
pkill -x ydotoold 2>/dev/null || true
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/.ydotool_socket"
systemctl --user reset-failed ydotoold.service 2>/dev/null || true
systemctl --user enable --now ydotoold.service
systemctl --user --no-pager --lines=0 status ydotoold.service | head -3 || true

# --- 2. whispr --user service ---------------------------------------------
say "Installing + starting the whispr --user service"
sed -e "s#@UV@#$UV_BIN#g" -e "s#@REPO@#$REPO_DIR#g" \
  "$REPO_DIR/systemd/whispr.service" > "$CONFIG_HOME/systemd/user/whispr.service"
systemctl --user daemon-reload
# Clear any prior failed/rate-limited state (e.g. from an earlier unit revision).
systemctl --user reset-failed whispr.service 2>/dev/null || true
systemctl --user enable --now whispr.service
sleep 8  # give the NPU model (~9s first compile) time to warm before status

# --- 2b. whispr-indicator --user service (status-bar tray icon) -----------
# Runs under system python (needs python3-gi + Ayatana AppIndicator); the lean
# inference venv deliberately lacks gi. Warn if those system packages are missing.
say "Installing + starting the whispr status-bar indicator"
if ! /usr/bin/python3 -c "import gi; gi.require_version('Gtk','3.0')" 2>/dev/null; then
  warn "python3-gi / GTK3 not found for /usr/bin/python3. Install with:"
  warn "  sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1"
  warn "then re-run this script. Skipping the indicator for now."
else
  sed -e "s#@REPO@#$REPO_DIR#g" \
    "$REPO_DIR/systemd/whispr-indicator.service" > "$CONFIG_HOME/systemd/user/whispr-indicator.service"
  systemctl --user daemon-reload
  systemctl --user reset-failed whispr-indicator.service 2>/dev/null || true
  systemctl --user enable --now whispr-indicator.service
  if ! gnome-extensions info ubuntu-appindicators@ubuntu.com 2>/dev/null | grep -qi 'State: ACTIVE'; then
    warn "The 'Ubuntu AppIndicators' GNOME extension isn't active — the tray icon"
    warn "may not show. Enable it: gnome-extensions enable ubuntu-appindicators@ubuntu.com"
  fi
fi

# --- 2c. dictation-copilot rewrite stage (cloud OpenAI, opt-in) ------------
# No extra service: the rewrite runs inline in the daemon via the OpenAI API.
# The daemon reads OPENAI_API_KEY from $CONFIG_HOME/whispr/whispr.env (a stable
# XDG path — the service must not depend on the repo's location). Seed that file
# from the repo .env if present, so a key in the dev tree "just works".
ENV_FILE="$CONFIG_HOME/whispr/whispr.env"
if [[ -f "$REPO_DIR/.env" ]] && grep -q '^OPENAI_API_KEY=' "$REPO_DIR/.env"; then
  if [[ ! -s "$ENV_FILE" ]] || ! grep -q '^OPENAI_API_KEY=' "$ENV_FILE"; then
    mkdir -p "$(dirname "$ENV_FILE")"
    grep '^OPENAI_API_KEY=' "$REPO_DIR/.env" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    say "Seeded $ENV_FILE with OPENAI_API_KEY from the repo .env"
  fi
fi
if grep -qs '^rewrite *= *true' "$CONFIG_HOME/whispr/config.toml" 2>/dev/null; then
  if [[ ! -s "$ENV_FILE" ]] && [[ -z "${OPENAI_API_KEY:-}" ]] \
     && ! grep -qs '^openai_api_key *= *"..*"' "$CONFIG_HOME/whispr/config.toml"; then
    warn "rewrite=true but no OpenAI API key found. Add one so the daemon can reach it:"
    warn "  printf 'OPENAI_API_KEY=sk-...\\n' > $ENV_FILE && chmod 600 $ENV_FILE"
    warn "Until then it pastes the raw transcript."
  fi
fi

# --- 3. Bind Super+W → whispr toggle --------------------------------------
say "Binding Super+W to 'whispr toggle' via gsettings"
KEYPATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/whispr/"
BASE="org.gnome.settings-daemon.plugins.media-keys"
LIST="$(gsettings get "$BASE" custom-keybindings)"
if [[ "$LIST" != *"$KEYPATH"* ]]; then
  if [[ "$LIST" == "@as []" || "$LIST" == "[]" ]]; then
    gsettings set "$BASE" custom-keybindings "['$KEYPATH']"
  else
    gsettings set "$BASE" custom-keybindings "${LIST%]*}, '$KEYPATH']"
  fi
fi
CBASE="$BASE.custom-keybinding:$KEYPATH"
# Point straight at the venv's console script: absolute path (GNOME's exec PATH may
# lack ~/.local/bin) and no `uv run` resolution overhead on every keypress.
WHISPR_BIN="$REPO_DIR/.venv/bin/whispr"
gsettings set "$CBASE" name 'whispr toggle'
gsettings set "$CBASE" command "$WHISPR_BIN toggle"
gsettings set "$CBASE" binding '<Super>w'
echo "Bound <Super>w → whispr toggle."

# --- 4. Verify NPU visibility + Daemon health -----------------------------
say "Verifying NPU visibility to OpenVINO"
DEVICES="$(uv run --project "$REPO_DIR" python -c \
  'import openvino as ov; print(",".join(ov.Core().available_devices))' 2>/dev/null || true)"
echo "OpenVINO devices: ${DEVICES:-<none/import failed>}"
if [[ "$DEVICES" == *NPU* ]]; then
  echo "NPU is visible — Whisper will run on the NPU."
else
  warn "NPU not listed. The Daemon will fall back to CPU. Check: you re-logged in"
  warn "(render group), and 'dmesg | grep -i vpu' for driver load errors."
fi

say "Reporting Daemon status"
uv run --project "$REPO_DIR" whispr status || warn "Daemon not answering yet; check: systemctl --user status whispr"

# --- Done ------------------------------------------------------------------
say "Setup complete"
echo "  • Super+W           → start/stop a Dictation"
echo "  • Tray icon         → live state + Start/stop/Cancel menu (top bar)"
echo "  • whispr status     → State + active device (NPU/CPU)"
echo "  • journalctl --user -u whispr -f   → Daemon logs (device won, load time)"
