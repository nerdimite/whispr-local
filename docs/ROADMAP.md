# whispr-local roadmap

## Shipped — v1 (MVP-0 + MVP-1)

- Warm daemon, `Super+W` toggle, record → transcribe → paste on Wayland (ADR-0001/0002).
- Whisper on the **Intel NPU** (whisper-small, ~0.3 s/utterance) with sticky NPU→CPU fallback.
- GNOME status-bar indicator (separate process, StatusNotifierItem).
- Silence gate, mic pinning, PortAudio self-heal.

Everything in `.cursor/plans/whispr-local-v1_*.plan.md` is complete. Items below are **v2**.

---

## "Dictation copilot" — transcript rewrite stage (cloud-first, shipped; local deferred)

**Problem.** Raw Whisper output is literal: no cleanup, wrong domain terms (hears "gate" for
"git", "nerd bite" for a product name), and blind to what's on screen — so a sentence dictated
into a code comment reads the same as one dictated into a chat box.

**Solution.** A post-transcription **rewrite stage** between `Transcriber` and `Injector`
(`transcript → rewrite → inject`), behind an injected `complete()` seam so the pure
prompt-assembly logic (`build_instructions` / `clean_reply`) is unit-testable and the LLM call is a
thin adapter. Three jobs:

1. **Cleanup.** Fix punctuation, casing, and remove disfluencies ("um", "you know", false starts)
   without changing meaning. ✅ shipped.
2. **Custom vocabulary.** A user-configured `vocabulary = [...]` of domain terms / proper nouns fed
   into the prompt so the model corrects mis-hearings toward the intended words. ✅ shipped.
3. **Screen context (vision).** Capture the screen and feed it to the model's vision path so it
   corrects garbled jargon toward on-screen terms and matches the register. ⚠️ shipped but off by
   default (`screen_context`): capture works (xdg portal, downscale to 2048px, delete-after) and the
   prompt actively scans the screen for sound-alikes, but two rough edges keep it opt-in — see
   backlog.

### Shipped now: cloud backend (OpenAI Responses API)

`src/whispr/rewriter.py` runs the transcript through **`gpt-5.4-nano`** (reasoning `effort: "none"`,
low verbosity — OpenAI's recommended latency-critical path; `gpt-5.4-mini` / `"low"` as a
quality-up). Off by default (`rewrite = false`); always falls back to the raw transcript on any API
failure/timeout, mirroring the Transcriber's validation discipline. Key via
`~/.config/whispr/whispr.env` (`OPENAI_API_KEY=…`, loaded by the systemd unit) or `openai_api_key`.

**Tradeoff (why this isn't the endgame):** cloud means the transcript **leaves the machine**, which
cuts against the project's on-device ethos. Acceptable as an opt-in MVP; the local backend below is
the target.

### Deferred: on-device Gemma 4 E2B (blocked on memory)

The intended endgame is **`google/gemma-4-E2B-it`** via OpenVINO GenAI's **`VLMPipeline`** (`gemma4`
arch) on the **iGPU (Arc)** — Whisper stays on the NPU, so no accelerator contention (VLMs aren't
NPU-supported anyway). This keeps everything local and unlocks the vision path.

**Blocker:** the int4 **export OOMs / hard-crashes this box** (30 GB RAM). The export loads the full
fp32 model + torch tracing into RAM and freezes the system. Export recipe that got furthest (all
three fixes needed, see memory `gemma4-export-recipe`): `optimum-intel@main` (released 2.0.0 predates
gemma4) + `transformers==5.5.0` (over optimum's stale `<5.1` cap) + `--task image-text-to-text` (E2B
auto-detects `any-to-any` via its audio tower, which the exporter rejects) + `TMPDIR` on real disk
(OpenVINO stages the fp16 IR through tmpfs `/tmp` and dies with `basic_ios::clear: iostream error`).
Still OOMs at the model-load/trace step regardless.

**Open questions before retrying local:**
- **Memory** — export on a bigger box / swap / a pre-exported IR from HF; and confirm *inference*
  memory on the iGPU fits (separate from export).
- **iGPU latency + version matrix** — gemma4 VLM support lands in openvino-genai **2026.2** (`gemma4`
  dir), separate from the 2025.3-pinned NPU-Whisper runtime, so it needs its own venv/process.
- **Vision on Wayland** — grab focused-window pixels (portal screenshot / grim) without a prompt each
  time; keep the vision step opt-in (privacy).
- **Prompt-injection safety** — screen text is untrusted; `build_instructions` already frames it as
  context to imitate, never instructions to follow.

---

## Backlog (smaller, independent)

- **Quiet screen capture** — the xdg-portal Screenshot triggers GNOME's shutter flash + sound on
  every capture (it calls the shell's screenshot handler; no per-call suppress). Replace with a
  **PipeWire screencast** session (what screen-sharing uses): no flash/sound, one-time "share your
  screen" approval at daemon start, then silent frame grabs. This is the blocker to turning
  `screen_context` on by default.
- **OCR screen context (vs. vision)** — nano's vision under-reads dense small text off the
  2048px-capped image (missed "we land"→"Wayland" until the prompt was pushed hard). OCR the
  **native-res** capture (Tesseract; Tesseract is accurate on crisp screen text — resolution, not
  density, was the problem) and feed the extracted text as cheap context — likely more reliable for
  jargon correction and works on a text-only model. `liteparse` bundles Tesseract but needs
  ImageMagick for images (or a Pillow PNG→PDF shim); plain `pytesseract` + system tesseract is the
  other option. Could also complement vision (text for exact strings, image for layout/register).
- **Push-to-talk mode** — hold `Super+W` to record, release to transcribe+paste (vs toggle).
- **Tray error state** — distinct indicator glyph when a transcription/paste fails (today: idle /
  recording / transcribing / down only).
- **Injection settle-delay tuning** (design open-Q #3) — verify paste reliability across apps; make
  the pre-paste delay configurable if flaky.
- **CI** — GitHub Actions running `pytest` on push.
- **Packaging** — one-shot installer (pipx / `.deb`) so it isn't tied to this repo path.
