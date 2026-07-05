# Local Whisper Dictation on NPU, Ubuntu

## Goal

A global hotkey dictation tool for Ubuntu 26.04 that runs entirely on device. Press a hotkey, speak, press it again, and the transcribed text gets pasted into whatever window has focus. No cloud, no subscription. This is the reason I want it: Wispr Flow doesn't ship a Linux build, and I want the same workflow running locally on the NPU in my ZenBook S14 (Intel Core Ultra 7 256V, Lunar Lake).

## Hardware and constraints

Laptop: ASUS ZenBook S14, Intel Core Ultra 7 256V, dual booting Ubuntu 26.04 LTS and Windows.
NPU: Intel's Lunar Lake NPU, rated around 48 TOPS.
The NPU only runs models compiled through OpenVINO's plugin system. There's no direct PyTorch to NPU path the way there is with CUDA.

## Why Whisper, not Gemma 4

I looked at running Gemma 4's native audio input on the NPU instead. Ruled it out for v1: NPU support for Gemma 4's smaller models (E2B, E4B) isn't shipped yet in OpenVINO, only CPU and preview GPU. Whisper on NPU works today with no caveats. Also Whisper's word error rate is meaningfully better for pure transcription (roughly 4.4% vs 13% for Gemma on the same benchmark), and Whisper handles long form audio natively while Gemma caps at 30 second clips.

Plan is to build Whisper on NPU first, then consider layering in a small local LLM (or Gemma 4 once NPU support lands) as a cleanup pass over the raw transcript, similar to what Wispr Flow does with its cloud model.

## What's already working (proof of concept, Python + pip)

I built a rough version with plain pip and two scripts, confirmed the approach is sound. Rebuilding properly with uv now. The rough version:

1. `record_toggle.py`: hotkey press starts `arecord` in the background (16kHz mono wav), writes its PID to a lock file. Second press kills the recording and calls the transcription script.
2. `transcribe.py`: loads the wav, runs it through `openvino_genai.WhisperPipeline` targeting `device="NPU"`, puts the resulting text on the clipboard via `xclip`, then simulates Ctrl+V via `xdotool` to paste into the focused window.
3. Hotkey bound through GNOME's Settings > Keyboard > Custom Shortcuts, calling `python3 ~/dictate/record_toggle.py`.

This confirmed the pipeline works end to end. What I want from a rebuild: proper project structure with uv, dependency management, a config file instead of hardcoded paths, and probably a cleaner recording approach than shelling out to arecord.

## Setup steps that matter (from testing)

Model export, using Optimum Intel:

```
optimum-cli export openvino --trust-remote-code --model openai/whisper-base ~/models/whisper-base-int8 --weight-format int8
```

Started with `whisper-base`. Good balance of speed and accuracy, can try `whisper-small` if accuracy needs improving.

Pinned versions that were needed for NPU compatibility (transformers version conflicts have caused Whisper export failures on other versions per OpenVINO's release notes):

```
nncf==2.18.0
onnx==1.18.0
optimum-intel==1.25.2
transformers==4.51.3
openvino==2026.2.1
openvino-tokenizers==2026.2.1
openvino-genai==2026.2.1
```

NPU driver needs to be 32.0.100.3104 or newer, otherwise inference fails silently or with unclear errors.

System deps needed outside the Python environment: `alsa-utils`, `xdotool`, `xclip`, `libnotify-bin` (for arecord, paste simulation, and clipboard, and desktop notifications).

## What I want from Claude Code

1. Set up the project with uv instead of a plain venv and pip, proper `pyproject.toml`, locked dependencies.
2. Rebuild the two scripts (recording toggle and transcription) as a clean small package rather than loose scripts, with a config file for model path and device (NPU vs CPU fallback).
3. Handle the NPU falling back to CPU gracefully if NPU init fails, rather than crashing.
4. Wire up the GNOME custom shortcut as part of setup instructions or an install script, not something I do by hand each time.
5. Keep it minimal. This is a personal tool, not a product yet. No need for a GUI, tray icon, or anything beyond the hotkey plus paste flow, at least for v1.

Later, separate task: adding an LLM cleanup pass on top of the raw transcript before pasting. Not part of this handoff, just flagging where this is headed.