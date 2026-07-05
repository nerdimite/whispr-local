from pathlib import Path

import pytest

from whispr import config


def _set_xdg(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    cache_home = tmp_path / "cache"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    return home, config_home, data_home, cache_home


def test_defaults_and_expansion(monkeypatch, tmp_path):
    home, config_home, data_home, cache_home = _set_xdg(monkeypatch, tmp_path)

    cfg = config.load()

    assert cfg.device == "NPU"
    assert cfg.notify is True
    assert cfg.dump_last_recording is False

    assert cfg.model_path == data_home / "whispr" / "models" / "whisper-base"
    assert cfg.cache_dir == cache_home / "whispr" / "ov"

    for p in (cfg.model_path, cfg.cache_dir):
        assert "~" not in str(p)
        assert "$" not in str(p)


def test_overlay_partial_toml_only_device(monkeypatch, tmp_path):
    home, config_home, data_home, cache_home = _set_xdg(monkeypatch, tmp_path)

    config_dir = config_home / "whispr"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('device = "cpu"\n')

    cfg = config.load()

    assert cfg.device == "CPU"
    assert cfg.notify is True
    assert cfg.dump_last_recording is False
    assert cfg.model_path == data_home / "whispr" / "models" / "whisper-base"
    assert cfg.cache_dir == cache_home / "whispr" / "ov"


def test_path_expansion_tilde(monkeypatch, tmp_path):
    home, config_home, data_home, cache_home = _set_xdg(monkeypatch, tmp_path)

    explicit_path = tmp_path / "custom_config.toml"
    explicit_path.write_text('model_path = "~/models/whisper-base"\n')

    cfg = config.load(explicit_path)

    assert cfg.model_path == home / "models" / "whisper-base"


def test_device_normalization_and_rejection(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)

    explicit_path = tmp_path / "bad_config.toml"
    explicit_path.write_text('device = "gpu"\n')

    with pytest.raises(ValueError):
        config.load(explicit_path)


def test_missing_default_file_returns_defaults(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)

    cfg = config.load()

    assert cfg == config.Config()


def test_explicit_missing_path_raises(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)

    missing = tmp_path / "does_not_exist.toml"

    with pytest.raises(FileNotFoundError):
        config.load(missing)


def test_invalid_toml_raises(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)

    bad = tmp_path / "invalid.toml"
    bad.write_text("this is not valid toml = = =")

    with pytest.raises(Exception):
        config.load(bad)
