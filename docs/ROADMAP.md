# whispr-local roadmap

## Shipped — v1 (MVP-0 + MVP-1)

- Warm daemon, `Super+\` toggle, record → transcribe → paste on Wayland (ADR-0001/0002).
- Whisper on the **Intel NPU** (whisper-small, ~0.3 s/utterance) with sticky NPU→CPU fallback.
- GNOME status-bar indicator (separate process, StatusNotifierItem).
- Silence gate, mic pinning, PortAudio self-heal.

Everything in `.cursor/plans/whispr-local-v1_*.plan.md` is complete. Items below are **v2**.

---

## Next (headline): "Dictation copilot" — on-device transcript rewrite with Gemma 4 E2B

**Problem.** Raw Whisper output is literal: no cleanup, wrong domain terms (hears "gate" for
"git", "nerd bite" for a product name), and blind to what's on screen — so a sentence dictated
into a code comment reads the same as one dictated into a chat box.

**Solution.** A post-transcription **rewrite stage**: pass the raw transcript through a small
**on-device multimodal VLM — `google/gemma-4-E2B-it`** (the efficient E-variant; `E4B-it` as a
quality-up option). It's supported by OpenVINO GenAI's **`VLMPipeline`** (`gemma4` architecture in
the VLM table), so it does three jobs in one pass, all locally (no cloud):

1. **Cleanup.** Fix punctuation, casing, and remove disfluencies ("um", "you know", false starts)
   without changing meaning. Off by default per-context if it ever over-edits.
2. **Custom vocabulary.** A user-configured list of domain terms / proper nouns / jargon
   (e.g. `git`, `OpenVINO`, `nerdimite`, `ydotool`) fed into the prompt so the model corrects
   mis-hearings toward the intended words. Config in `~/.config/whispr/config.toml`
   (e.g. `vocabulary = ["git", "OpenVINO", ...]`), possibly with phonetic hints.
3. **Screen context (vision).** Capture the focused window (or a region) and feed it to Gemma 3n's
   vision path so the rewrite matches the surrounding text — tone, terminology, whether it's code
   vs prose vs a chat reply. E.g. dictating into a terminal yields a command; into a doc yields a
   sentence.

**Where it fits.** New stage between `Transcriber` and `Injector` in the daemon
(`transcript → rewrite(context) → inject`), behind an injected seam like the others so the pure
prompt-assembly logic is unit-testable and the `VLMPipeline` call is a thin adapter. Reuses the
warm-daemon pattern: keep Gemma resident alongside Whisper.

**Device split (nice property).** The VLMPipeline runs on **CPU or GPU — NPU is not supported for
VLMs** in genai. On Lunar Lake that's a clean division of labour: **Whisper stays on the NPU, Gemma
runs on the iGPU (Arc)**, so the two models don't contend for one accelerator.

**Open questions / spikes before committing:**
- **iGPU latency + version matrix** — confirm `gemma-4-E2B-it` exports and runs on the Lunar Lake
  iGPU via `VLMPipeline`, at what latency, and under which openvino-genai/optimum-intel/transformers
  pins (same version-matrix risk we hit with Whisper — see memory `npu-whisper-working`; note the
  runtime is pinned to the 2025.3 line for the NPU-Whisper path, so check Gemma-4 VLM support exists
  there or whether the two need different genai builds / processes). Budget: whole rewrite sub-second.
- **Vision on Wayland** — how to grab the focused-window pixels (portal screenshot API / grim +
  the active window geometry) without a disruptive permission prompt each time; privacy implications
  of screenshotting (never leaves the machine; make the vision step explicitly opt-in).
- **Latency vs quality** — E2B vs E4B; token budget; whether cleanup+vocab (text-only) should be a
  fast default and screen-context a heavier opt-in mode.
- **Prompt-injection safety** — screen text is untrusted input to the rewrite prompt; the model must
  treat it as context to imitate, not instructions to follow.
- **Failure mode** — if rewrite fails or times out, fall back to injecting the raw Whisper transcript
  (never block a dictation on the LLM). Mirror the Transcriber's validation/fallback discipline.

**Suggested path:** `grill-me` the open questions → spike `gemma-4-E2B-it` on the iGPU via
`VLMPipeline` → `to-design` → `to-plan` → TDD build (text-only cleanup+vocab first as a tracer
bullet, screen-context as a second slice).

---

## Backlog (smaller, independent)

- **Push-to-talk mode** — hold `Super+\` to record, release to transcribe+paste (vs toggle).
- **Tray error state** — distinct indicator glyph when a transcription/paste fails (today: idle /
  recording / transcribing / down only).
- **Injection settle-delay tuning** (design open-Q #3) — verify paste reliability across apps; make
  the pre-paste delay configurable if flaky.
- **CI** — GitHub Actions running `pytest` on push.
- **Packaging** — one-shot installer (pipx / `.deb`) so it isn't tied to this repo path.
