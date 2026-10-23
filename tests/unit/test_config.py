import pytest

from aalu.services.config import ConfigError, load_config, parse_config
from conftest import ROOT


def test_dev_config_loads():
    cfg = load_config(ROOT / "config" / "dev.toml")
    assert cfg.gnss["adapter"] == "fake"
    assert cfg.freshness["gnss"].stale_after_s == 3
    assert any(r.id == "battery.soc_low" for r in cfg.alarm_rules)


def test_pi_example_config_loads():
    cfg = load_config(ROOT / "config" / "pi.toml.example")
    assert cfg.drive_window.fullscreen and cfg.camper_window.fullscreen


def test_bad_alarm_rule_is_a_config_error():
    with pytest.raises(ConfigError):
        parse_config({"alarms": [{"id": "x"}]})


def test_defaults():
    cfg = parse_config({})
    assert cfg.camper_window.screen == 1
    assert cfg.navigation_command == []
    assert cfg.screen_layout == "auto"
    assert cfg.drive_window.fullscreen  # adapts to whatever screen is attached


def test_invalid_layout_rejected():
    with pytest.raises(ConfigError):
        parse_config({"ui": {"layout": "triple"}})


def test_relative_paths_resolve_against_base_dir(tmp_path):
    cfg_file = tmp_path / "c.toml"
    cfg_file.write_text('[adapters.gnss]\nadapter = "fake"\nroute = "r.json"\n')
    cfg = load_config(cfg_file, base_dir=ROOT)
    assert cfg.resolve("r.json") == ROOT / "r.json"


def test_dashcam_defaults_and_window_validation():
    cfg = load_config(ROOT / "config" / "dev.toml")
    assert cfg.video.retention_h == 5
    assert (cfg.video.long_protect_before_s, cfg.video.long_protect_after_s) == (300, 600)
    with pytest.raises(ConfigError):  # a save must not reach back beyond what is kept
        parse_config({"video": {"retention_h": 0.05, "long_protect_before_s": 300}})
