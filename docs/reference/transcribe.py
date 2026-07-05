#!/usr/bin/env python3
"""
Loads the recorded WAV file, runs it through Whisper on the NPU via
OpenVINO GenAI, and pastes the result into whatever window is focused.
"""
import wave
import subprocess
import numpy as np
import openvino_genai as ov_genai

AUDIO_FILE = "/tmp/dictate.wav"
MODEL_DIR = "/home/YOUR_USERNAME/models/whisper-base-int8"  # update this path
DEVICE = "NPU"  # fall back to "CPU" if NPU errors out


def load_audio(path):
    with wave.open(path, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def paste_text(text):
    # Put text on clipboard, then simulate paste. More reliable than
    # simulating keystrokes for punctuation-heavy text.
    subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode())
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"])


def main():
    pipe = ov_genai.WhisperPipeline(MODEL_DIR, device=DEVICE)
    audio = load_audio(AUDIO_FILE)
    result = pipe.generate(audio)
    text = str(result).strip()
    if text:
        paste_text(text)
        subprocess.run(["notify-send", "Dictate", text[:80]])
    else:
        subprocess.run(["notify-send", "Dictate", "No speech detected"])


if __name__ == "__main__":
    main()
