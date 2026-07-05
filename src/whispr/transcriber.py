"""Whisper transcription with sticky NPU-to-CPU device fallback.

Device selection happens exactly once, at Transcriber construction time.
If the configured device (default "NPU") fails to initialize, we fall back
to "CPU" and notify the caller — but we never re-probe. `transcribe` is a
pure call over the already-warm pipeline.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


def make_whisper_pipeline(device: str, config: Any):
    """Real pipeline factory. Lazily imports openvino_genai so this module
    can be imported without the OpenVINO/NPU stack installed."""
    import openvino_genai

    return openvino_genai.WhisperPipeline(
        str(config.model_path),
        device=device,
        CACHE_DIR=str(config.cache_dir),
    )


class Transcriber:
    def __init__(
        self,
        config: Any,
        pipeline_factory: Callable[[str, Any], Any] = make_whisper_pipeline,
        notify: Optional[Callable[[str], None]] = None,
    ):
        self._config = config
        self._pipeline_factory = pipeline_factory
        self._notify = notify

        requested_device = getattr(config, "device", "NPU")

        if requested_device == "CPU":
            self._pipeline = self._build_validated("CPU")
            self.active_device = "CPU"
            return

        try:
            self._pipeline = self._build_validated(requested_device)
            self.active_device = requested_device
        except Exception:
            # Covers BOTH init-time failures (device won't compile the model) AND
            # inference-time failures surfaced by the validation decode — e.g. the
            # NPU Whisper path where compile succeeds but generate() throws. Without
            # the validation decode this would only blow up mid-Dictation.
            self._pipeline = self._build_validated("CPU")
            self.active_device = "CPU"
            if callable(self._notify):
                self._notify("NPU unavailable — using CPU")

    def _build_validated(self, device: str):
        """Build the pipeline for `device` and prove it can actually decode.

        Runs one throwaway decode over a short silent buffer so an NPU that compiles
        but fails at inference is caught here (→ fallback) instead of on the user's
        first real Dictation.
        """
        import numpy as np

        pipeline = self._pipeline_factory(device, self._config)
        pipeline.generate(np.zeros(16000, dtype=np.float32))  # 1 s silence
        return pipeline

    def transcribe(self, buffer) -> str:
        result = self._pipeline.generate(buffer)
        if hasattr(result, "texts"):
            text = result.texts[0] if result.texts else ""
        else:
            text = str(result)
        return text.strip()
