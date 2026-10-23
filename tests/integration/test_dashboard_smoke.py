"""Starts the real dashboard offscreen and fails on any QML warning (G1/G2)."""

import os
import subprocess
import sys

import pytest

from conftest import ROOT

pytestmark = pytest.mark.qt

SIZES = [(800, 480), (1024, 600), (1280, 800), (1920, 1080), (720, 1280)]


def run_dashboard(tmp_path, width, height, *args):
    base = (ROOT / "config" / "dev.toml").read_text()
    # Redefining a TOML table is invalid, so rewrite the window sizes in place.
    cfg = base.replace("width = 1280", f"width = {width}")
    for h in ("height = 720", "height = 800"):
        cfg = cfg.replace(h, f"height = {height}")
    path = tmp_path / "cfg.toml"
    path.write_text(cfg)
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen",
           "XDG_CONFIG_HOME": str(tmp_path / "xdg"),   # don't touch the user's saved layout
           "XDG_CACHE_HOME": str(tmp_path / "cache")}
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "apps" / "dashboard" / "main.py"), "--config", str(path),
         "--quit-after", "3", "--screenshot-dir", str(tmp_path), *args],
        env=env, capture_output=True, text=True, timeout=60,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "QML" not in output.replace("QML_", ""), output
    return output


@pytest.mark.parametrize(("width", "height"), SIZES, ids=[f"{w}x{h}" for w, h in SIZES])
@pytest.mark.parametrize("view", ["drive", "camper"])
def test_single_window_starts_without_qml_warnings(tmp_path, width, height, view):
    run_dashboard(tmp_path, width, height, "--layout", "single", "--view", view)
    assert (tmp_path / "single.png").exists()


def test_dual_windows_start_without_qml_warnings(tmp_path):
    run_dashboard(tmp_path, 1280, 720, "--layout", "dual")
    assert (tmp_path / "drive.png").exists() and (tmp_path / "camper.png").exists()


@pytest.mark.parametrize("layout", ["map", "energy"])
def test_drive_layouts_and_degraded_data(tmp_path, layout):
    conf = tmp_path / "xdg" / "aalu" / "aalu-dashboard.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(f"[drive]\nlayout={layout}\n")
    run_dashboard(tmp_path, 1280, 720, "--layout", "single",
                  "--sim", "gnss_fix=false", "--sim", "victron_connected=false",
                  "--sim", "phone_connected=false", "--sim", "reverse=true")
