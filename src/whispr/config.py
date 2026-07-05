"""Configuration loading for whispr.

This module has no dependency on any other ``whispr`` module: it is a pure,
self-contained unit whose only I/O is reading an optional TOML file from
disk. Keep it that way so it stays trivially unit-testable in isolation.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

_ALLOWED_DEVICES = {"NPU", "CPU"}


def _xdg_path(env_var: str, fallback: str) -> Path:
    base = os.environ.get(env_var)
    if base:
        return Path(base)
    return Path(os.path.expanduser("~")) / fallback


def _default_config_file() -> Path:
    return _xdg_path("XDG_CONFIG_HOME", ".config") / "whispr" / "config.toml"


def _default_model_path() -> Path:
    return _xdg_path("XDG_DATA_HOME", ".local/share") / "whispr" / "models" / "whisper-base"


def _default_cache_dir() -> Path:
    return _xdg_path("XDG_CACHE_HOME", ".cache") / "whispr" / "ov"


def _expand_path(value: str | os.PathLike) -> Path:
    expanded = os.path.expanduser(os.path.expandvars(str(value)))
    return Path(expanded)


def _normalize_device(value: str) -> str:
    normalized = str(value).strip().upper()
    if normalized not in _ALLOWED_DEVICES:
        raise ValueError(
            f"Invalid device {value!r}: expected one of {sorted(_ALLOWED_DEVICES)} "
            "(case-insensitive)"
        )
    return normalized


@dataclass
class Config:
    device: str = "NPU"
    model_path: Path = field(default_factory=_default_model_path)
    cache_dir: Path = field(default_factory=_default_cache_dir)
    dump_last_recording: bool = False
    notify: bool = True
    # Capture device for sounddevice: None = system default, an int index, or a
    # substring of the device name (e.g. "Digital Microphone"). Pin this so a
    # bluetooth headset connecting/disconnecting can't silently steal the default.
    input_device: str | int | None = None
    # RMS below this ⇒ treat the capture as silence (skip Whisper, which otherwise
    # hallucinates whole phantom sentences on near-silence/ambient). Default sits above
    # a typical laptop-mic noise floor; tune from the daemon's logged rms if speech is
    # dropped (lower it) or ambient still transcribes (raise it).
    silence_threshold: float = 0.02
    # --- dictation-copilot rewrite stage (cloud OpenAI for now, see ROADMAP) --
    # Off by default. When true the daemon runs the transcript through a cloud
    # LLM for cleanup + vocabulary correction before pasting. NOTE: this sends
    # the transcript OFF the machine (on-device Gemma is deferred — it OOMs here).
    # Always falls back to the raw transcript on any API failure/timeout.
    rewrite: bool = False
    # Domain terms / proper nouns fed into the rewrite prompt so mis-hearings are
    # corrected toward the intended spelling (e.g. ["git", "CellStrat"]).
    vocabulary: list[str] = field(default_factory=list)
    # Opt-in screen-context vision (not captured/sent unless explicitly enabled).
    screen_context: bool = False
    # OpenAI model + reasoning effort. nano @ effort "none" is the fast default
    # (simple cleanup, no reasoning); bump to gpt-5.4-mini / effort "low" for
    # more accuracy at the cost of latency.
    rewriter_model: str = "gpt-5.4-nano"
    rewrite_effort: str = "none"
    # API key: prefer this, else $OPENAI_API_KEY. Leave empty to use the env var.
    openai_api_key: str = ""
    # Hard deadline on the rewrite round-trip; on expiry the raw transcript is
    # injected instead (a dictation never blocks on the LLM).
    rewrite_timeout: float = 10.0

    def __post_init__(self) -> None:
        self.device = _normalize_device(self.device)
        self.model_path = _expand_path(self.model_path)
        self.cache_dir = _expand_path(self.cache_dir)
        self.vocabulary = [str(term) for term in self.vocabulary]


def load(path: str | os.PathLike | None = None) -> Config:
    """Load configuration, overlaying defaults with an optional TOML file.

    - If ``path`` is None and the default config file does not exist, return
      an all-defaults ``Config``.
    - If ``path`` is explicitly given and does not exist, raise
      ``FileNotFoundError``.
    - Any fields present in the TOML file override the corresponding
      defaults; fields absent from the file keep their defaults.
    """
    explicit = path is not None
    config_path = Path(path) if explicit else _default_config_file()

    if not config_path.exists():
        if explicit:
            raise FileNotFoundError(f"Config file not found: {config_path}")
        return Config()

    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise tomllib.TOMLDecodeError(
            f"Invalid TOML in config file {config_path}: {exc}"
        ) from exc

    valid_fields = {f.name for f in fields(Config)}
    unknown = set(data) - valid_fields
    overrides = {k: v for k, v in data.items() if k in valid_fields}
    if unknown:
        # Ignore unknown keys silently is risky; keep it explicit but non-fatal
        # for forward-compat. Comment kept for clarity only.
        pass

    return Config(**overrides)
