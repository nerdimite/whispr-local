from types import SimpleNamespace

import pytest

from whispr.transcriber import Transcriber


class FakePipeline:
    def __init__(self, device, text="hello world", bad_inference=False):
        self.device = device
        self.text = text
        self.generate_calls = 0
        self._bad_inference = bad_inference

    def generate(self, buffer):
        self.generate_calls += 1
        if self._bad_inference:
            raise RuntimeError(f"{self.device} inference failed")
        return self.text


def make_fake_factory(fail_devices=(), bad_inference_devices=(), text="hello world"):
    """Returns (factory, calls) where calls is a dict tracking invocation counts.

    `fail_devices` raise at build; `bad_inference_devices` build fine but raise on
    generate() (models the NPU-compiles-but-can't-infer case).
    """
    calls = {}

    def factory(device, config):
        calls[device] = calls.get(device, 0) + 1
        if device in fail_devices:
            raise RuntimeError(f"{device} unavailable")
        return FakePipeline(device, text=text, bad_inference=device in bad_inference_devices)

    return factory, calls


def test_npu_failure_falls_back_to_cpu():
    cfg = SimpleNamespace(device="NPU", model_path="model", cache_dir="cache")
    factory, calls = make_fake_factory(fail_devices=("NPU",), text="fallback text")
    notifications = []

    t = Transcriber(cfg, pipeline_factory=factory, notify=notifications.append)

    assert t.active_device == "CPU"
    assert t.transcribe(b"buffer") == "fallback text"
    assert len(notifications) == 1

    assert calls == {"NPU": 1, "CPU": 1}

    t.transcribe(b"buffer")
    assert calls == {"NPU": 1, "CPU": 1}


def test_npu_inference_failure_falls_back_to_cpu():
    # NPU compiles fine but generate() throws (the real openvino-genai NPU Whisper
    # case). The startup validation decode must catch it and fall back to CPU.
    cfg = SimpleNamespace(device="NPU", model_path="model", cache_dir="cache")
    factory, calls = make_fake_factory(bad_inference_devices=("NPU",), text="cpu text")
    notifications = []

    t = Transcriber(cfg, pipeline_factory=factory, notify=notifications.append)

    assert t.active_device == "CPU"
    assert t.transcribe(b"buffer") == "cpu text"
    assert len(notifications) == 1
    assert calls == {"NPU": 1, "CPU": 1}


def test_cpu_config_skips_npu():
    cfg = SimpleNamespace(device="CPU", model_path="model", cache_dir="cache")
    factory, calls = make_fake_factory(fail_devices=(), text="cpu text")
    notifications = []

    t = Transcriber(cfg, pipeline_factory=factory, notify=notifications.append)

    assert t.active_device == "CPU"
    assert t.transcribe(b"buffer") == "cpu text"
    assert calls == {"CPU": 1}
    assert notifications == []
