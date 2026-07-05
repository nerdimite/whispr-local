#!/usr/bin/env bash
# Export an OpenVINO Whisper model into the XDG data dir the Daemon reads.
#
# NPU Whisper is EXPORT-VERSION-SENSITIVE. The genai runtime (2025.3) needs the
# decoder exported so its self-attention carries an explicit sliced causal mask
# (SDPA + Slice on the attn-mask port). transformers >= 4.53 emit the `is_causal`
# flag form instead, which makes the NPU static pipeline fail at compile with
# `Check '!self_attn_nodes.empty()' failed` — and even a graph that compiles then
# throws `Port for tensor name attention_mask was not found` at generate() unless
# the whole export stack matches the 2025.3 runtime. So we pin the export stack
# hard and, critically, use --disable-stateful (the "decoder-with-past" form is
# the one that runs on the NPU; the stateful form is a 2026.x path that is broken
# on Lunar Lake today).
#
# This runs in an EPHEMERAL uv venv so none of torch/transformers/optimum/nncf
# ever land in the lean inference runtime (.venv). Idempotent: skips if exported.
set -euo pipefail

MODEL_ID="${1:-openai/whisper-base}"
WEIGHT_FORMAT="${2:-int8}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
OUT_DIR="$DATA_HOME/whispr/models/$(basename "$MODEL_ID")"

if [[ -f "$OUT_DIR/openvino_encoder_model.xml" ]]; then
  echo "Model already exported at: $OUT_DIR"
  exit 0
fi

if ! command -v uv >/dev/null; then
  echo "uv not found on PATH (https://docs.astral.sh/uv/). Install it and re-run." >&2
  exit 1
fi

# --- pinned, 2025.3-matched export stack (see header) ----------------------
# transformers is capped at 4.52.4 on purpose — do not bump without re-testing
# NPU generate(). torch is CPU-only (no CUDA wheels). openvino matches the runtime.
EXPORT_REQS=(
  "openvino==2025.3.0"
  "openvino-tokenizers==2025.3.0.0"
  "transformers==4.52.4"
  "optimum-intel[nncf]==1.25.2"
  "torch==2.5.1"
  "Pillow"       # optimum.intel.openvino.quantization imports PIL at module load
  "requests"     # optimum.exporters.tasks imports requests
)

VENV="$(mktemp -d)/export-venv"
cleanup() { rm -rf "$(dirname "$VENV")"; }
trap cleanup EXIT

echo "Building ephemeral export env (transformers 4.52.4 stack, CPU torch)…"
uv venv "$VENV" --python 3.12 >/dev/null
VIRTUAL_ENV="$VENV" uv pip install --python "$VENV/bin/python" \
  --index-strategy unsafe-best-match \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  "${EXPORT_REQS[@]}"

echo "Exporting $MODEL_ID -> $OUT_DIR (weight-format=$WEIGHT_FORMAT, disable-stateful)…"
mkdir -p "$OUT_DIR"
"$VENV/bin/optimum-cli" export openvino \
  --trust-remote-code \
  --disable-stateful \
  --weight-format "$WEIGHT_FORMAT" \
  --model "$MODEL_ID" \
  "$OUT_DIR"

echo "Done. Model runs on the NPU (falls back to CPU automatically if unavailable)."
echo "If you exported a non-default model, set model_path in ~/.config/whispr/config.toml."
