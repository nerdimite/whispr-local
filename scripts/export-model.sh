#!/usr/bin/env bash
# Export an OpenVINO Whisper model (int8) into the XDG data dir the Daemon reads.
# Idempotent: skips if the target already has an OpenVINO model.
set -euo pipefail

MODEL_ID="${1:-openai/whisper-base}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
OUT_DIR="$DATA_HOME/whispr/models/$(basename "$MODEL_ID")"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$OUT_DIR/openvino_encoder_model.xml" ]]; then
  echo "Model already exported at: $OUT_DIR"
  exit 0
fi

echo "Exporting $MODEL_ID → $OUT_DIR (int8)…"
mkdir -p "$OUT_DIR"

# optimum-cli ships with the `npu` extra; run it inside the project env.
uv run --project "$REPO_DIR" --extra npu \
  optimum-cli export openvino \
  --model "$MODEL_ID" \
  --weight-format int8 \
  "$OUT_DIR"

echo "Done. Set model_path in ~/.config/whispr/config.toml if you used a non-default model."
