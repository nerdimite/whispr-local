#!/usr/bin/env bash
# whispr-local setup — PHASE 1 (system / privileged). Run this FIRST.
#
# Does everything that needs sudo or a group change: APT deps, /dev/uinput access,
# `input` + `render` group membership, the Intel NPU userspace driver, the Python
# environment, and (optionally) the Whisper model export.
#
# Group changes only take effect after a re-login, so the service enablement, hotkey
# binding, and NPU verification live in PHASE 2 (scripts/setup-user.sh). This script
# ends by telling you to log out, back in, then run phase 2.
#
# Every privileged (sudo) action is announced before it runs.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
MODEL_DIR="$DATA_HOME/whispr/models/whisper-base"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*"; }
sudo_run() {
  printf '\033[1;31m[sudo]\033[0m %s\n' "$*"
  sudo "$@"
}

# --- 1. APT system dependencies -------------------------------------------
say "Installing APT dependencies"
APT_PKGS=(
  libportaudio2          # sounddevice / PortAudio capture
  wl-clipboard           # wl-copy (Injection, ADR-0002)
  ydotool                # paste simulation via /dev/uinput
  libnotify-bin          # notify-send
  libayatana-appindicator3-1        # tray icon (MVP-1)
  gir1.2-ayatanaappindicator3-0.1
  # NPU userspace-driver runtime deps:
  libze1 libtbb12 libzstd1 zlib1g
)
sudo_run apt-get update
sudo_run apt-get install -y "${APT_PKGS[@]}"

# --- 2. /dev/uinput access + groups ---------------------------------------
say "Configuring /dev/uinput access (udev rule) + input/render groups"
UDEV_RULE='KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"'
UDEV_PATH=/etc/udev/rules.d/80-whispr-uinput.rules
if [[ "$(cat "$UDEV_PATH" 2>/dev/null || true)" != "$UDEV_RULE" ]]; then
  echo "$UDEV_RULE" | sudo_run tee "$UDEV_PATH" >/dev/null
  sudo_run udevadm control --reload-rules
  sudo_run udevadm trigger
fi
# `input` → /dev/uinput (ydotool paste). `render` → /dev/accel/accel0 (NPU).
for grp in input render; do
  if ! id -nG "$USER" | tr ' ' '\n' | grep -qx "$grp"; then
    sudo_run usermod -aG "$grp" "$USER"
  fi
done

# --- 3. Intel NPU userspace driver ----------------------------------------
# The kernel side (intel_vpu, /dev/accel/accel0) ships with the kernel; the Level
# Zero userspace driver that OpenVINO compiles Whisper onto does NOT, and Ubuntu
# doesn't package it — install it from intel/linux-npu-driver releases.
say "Installing the Intel NPU userspace driver"
if dpkg -l intel-level-zero-npu 2>/dev/null | grep -q '^ii'; then
  echo "NPU userspace driver already installed ($(dpkg-query -W -f='${Version}' intel-level-zero-npu))."
else
  TMP="$(mktemp -d)"
  URL="$(curl -fsSL https://api.github.com/repos/intel/linux-npu-driver/releases/latest \
        | grep browser_download_url | grep 'ubuntu2404.tar.gz' | sed 's/.*: "//;s/"//' | head -n1)"
  if [[ -z "$URL" ]]; then
    warn "Could not resolve an NPU driver release asset. Install manually from"
    warn "https://github.com/intel/linux-npu-driver/releases and re-run."
  else
    echo "Downloading $(basename "$URL")"
    curl -fsSL -o "$TMP/npu.tar.gz" "$URL"
    tar xzf "$TMP/npu.tar.gz" -C "$TMP"
    # Install order: firmware → level-zero → compiler. dbgsym .ddeb files are skipped.
    sudo_run dpkg -i "$TMP"/intel-fw-npu_*.deb \
                     "$TMP"/intel-level-zero-npu_*.deb \
                     "$TMP"/intel-driver-compiler-npu_*.deb
    sudo_run apt-get install -f -y   # satisfy anything dpkg left unmet
  fi
  rm -rf "${TMP:-/nonexistent}"
fi
# NOTE: the tarball targets ubuntu2404; on a newer Ubuntu the deps above still
# resolve (all are lower-bound version requirements). If NPU init later fails,
# check `dmesg | grep -i vpu` and the driver release notes.

# --- 4. Python environment (uv) -------------------------------------------
say "Syncing Python environment (uv, with the NPU extra)"
if ! command -v uv >/dev/null; then
  warn "uv not found on PATH. Install it (https://docs.astral.sh/uv/) and re-run."
  exit 1
fi
uv sync --project "$REPO_DIR" --extra npu

# --- 5. Offer to export the Whisper model ---------------------------------
if [[ ! -f "$MODEL_DIR/openvino_encoder_model.xml" ]]; then
  say "No Whisper model found at $MODEL_DIR"
  read -r -p "Export openai/whisper-base now (int8, runs on the NPU)? [Y/n] " ans
  if [[ "${ans:-Y}" =~ ^[Yy]?$ ]]; then
    "$REPO_DIR/scripts/export-model.sh"
  else
    echo "Skipped. Run scripts/export-model.sh (or phase 2 will remind you)."
  fi
else
  echo "Model present at $MODEL_DIR."
fi

# --- Done: hand off to phase 2 --------------------------------------------
say "Phase 1 complete"
printf '\n\033[1;33m*** LOG OUT AND BACK IN NOW ***\033[0m\n'
printf 'Your user was added to the '\''input'\'' and '\''render'\'' groups; ydotool paste and\n'
printf 'NPU access do not work until you re-login.\n\n'
printf 'Then finish setup with:\n  \033[1mbash %s/scripts/setup-user.sh\033[0m\n' "$REPO_DIR"
