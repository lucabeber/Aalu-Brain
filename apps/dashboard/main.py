"""AALU dashboard entry point: two windows (drive, camper) over one Vehicle Core.

    python apps/dashboard/main.py --config config/dev.toml
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))  # run from a checkout without installing

import shiboken6  # noqa: E402
from PySide6.QtCore import QStandardPaths, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication, QScreen, QWindow  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402

from aalu.maps.pack import find_packs  # noqa: E402
from aalu.maps.server import MapServer  # noqa: E402
from aalu.services.config import (  # noqa: E402
    SCREEN_LAYOUTS,
    AppConfig,
    WindowConfig,
    load_config,
)
from aalu.services.tile_proxy import TileProxy  # noqa: E402
from aalu.services.vehicle_core import VehicleCore  # noqa: E402
from aalu.ui.bridge import Backend  # noqa: E402

QML_MAIN = Path(__file__).resolve().parent / "qml" / "Main.qml"
log = logging.getLogger("aalu")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AALU on-board dashboards")
    p.add_argument("--config", default=str(ROOT / "config" / "dev.toml"))
    p.add_argument("--layout", choices=SCREEN_LAYOUTS,
                   help="override [ui] layout: auto = one window per screen (max 2), "
                        "single = one window with Drive/Camper switch, dual = two windows")
    p.add_argument("--only", choices=("drive", "camper"), help="open only this view")
    p.add_argument("--view", choices=("drive", "camper"), default="drive",
                   help="view shown first in a single window")
    p.add_argument("--page", default="energy",
                   help="camper page shown first (energy, water, lights, audio, dashcam, ...)")
    p.add_argument("--quit-after", type=float, metavar="S",
                   help="exit after S seconds (smoke tests)")
    p.add_argument("--screenshot-dir", metavar="DIR",
                   help="with --quit-after: save a PNG of each window before exiting")
    p.add_argument("--sim", action="append", default=[], metavar="KEY=BOOL",
                   help="initial simulation scenario, e.g. --sim gnss_fix=false (repeatable)")
    p.add_argument("--search", metavar="QUERY",
                   help="search a destination at startup (testing/demo; bypasses the drive lock)")
    p.add_argument("--go", action="store_true", help="with --search: route to the first result")
    p.add_argument("--panel", choices=("route", "trips", "gpx"),
                   help="open the navigation panel on this tab at startup (testing/demo)")
    p.add_argument("--gpx", metavar="FILE", help="load a GPX file of the library at startup "
                   "(path relative to the GPX folder; testing/demo)")
    p.add_argument("--map-engine", choices=("auto", "maplibre", "qtlocation"),
                   help="override [map] engine")
    p.add_argument("--keyboard", choices=("on", "off"),
                   help="override [ui] virtual_keyboard (on-screen keyboard)")
    p.add_argument("--log-level", default=os.environ.get("AALU_LOG_LEVEL", "INFO"))
    return p.parse_args(argv)


def place_window(window: QWindow, cfg: WindowConfig, screens: list[QScreen], name: str) -> None:
    if cfg.screen < len(screens):
        screen = screens[cfg.screen]
    else:
        # Degraded: the configured monitor is missing. Keep running on the first one.
        log.warning("%s: screen %d not present (%d found), using screen 0",
                    name, cfg.screen, len(screens))
        screen = screens[0]
    window.setScreen(screen)
    geo = screen.geometry()
    if cfg.fullscreen:
        window.setGeometry(geo)
        window.showFullScreen()
    else:
        x = geo.x() + (cfg.x if cfg.x is not None else 0)
        y = geo.y() + (cfg.y if cfg.y is not None else 0)
        window.setGeometry(x, y, cfg.width, cfg.height)
        window.show()


def resolve_windows(config: AppConfig, layout: str, only: str | None,
                    screen_count: int) -> list[tuple[str, WindowConfig]]:
    """Which windows to open: ``single`` = both views in one window (one touchscreen)."""
    if only:
        return [(only, config.drive_window if only == "drive" else config.camper_window)]
    if layout == "auto":
        layout = "dual" if screen_count >= 2 else "single"
    if layout == "single":
        return [("single", config.drive_window)]
    return [("drive", config.drive_window), ("camper", config.camper_window)]


def create_windows(engine: QQmlApplicationEngine, config: AppConfig, layout: str,
                   only: str | None, view: str = "drive",
                   page: str = "energy") -> dict[str, QWindow]:
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_MAIN)))
    if component.isError():
        raise RuntimeError("\n".join(e.toString() for e in component.errors()))

    screens = QGuiApplication.screens()
    log.info("screens: %s", ", ".join(
        f"{s.name()} {s.geometry().width()}x{s.geometry().height()}" for s in screens))
    windows: dict[str, QWindow] = {}
    for name, cfg in resolve_windows(config, layout, only, len(screens)):
        props = {"screenName": name, "camperPage": page}
        if name == "single":
            props["view"] = view
        obj = component.createWithInitialProperties(props)
        if obj is None:
            raise RuntimeError("\n".join(e.toString() for e in component.errors()))
        # Python owns `obj`: the dict keeps the window alive (and the JS GC away).
        assert isinstance(obj, QWindow)
        place_window(obj, cfg, screens, name)
        windows[name] = obj
    return windows


def resolve_map_engine(config: AppConfig, override: str | None) -> str:
    """MapLibre (offline vector packs) when packs exist and QtWebEngine is available."""
    engine = override or config.map.engine
    if engine == "qtlocation":
        return engine
    try:
        import PySide6.QtWebEngineQuick  # noqa: F401
    except ImportError:
        log.warning("QtWebEngine not available: using the Qt Location map")
        return "qtlocation"
    if engine == "maplibre":
        return engine
    packs = find_packs(config.resolve(config.map.maps_dir))
    return "maplibre" if any(p.has("map") for p in packs) else "qtlocation"


def start_search(core: VehicleCore, query: str, go: bool) -> None:
    """Search once a GNSS position exists (results are ranked around it)."""
    nav = core.navigation

    def chosen_once() -> None:
        view = nav.view()
        if go and view["search"]["state"] == "done" and view["route"]["state"] == "none":
            core.choose_destination(0)

    def try_search() -> None:
        if core.position() is None:
            QTimer.singleShot(500, try_search)
            return
        nav.subscribe(chosen_once)
        nav.search(query, core.position())

    QTimer.singleShot(500, try_search)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    p_engine = args.map_engine
    config = load_config(args.config, base_dir=ROOT)
    if args.keyboard:
        config = dataclasses.replace(config, virtual_keyboard=args.keyboard == "on")
    if config.virtual_keyboard:
        os.environ["QT_IM_MODULE"] = "qtvirtualkeyboard"  # must be set before QGuiApplication
    engine_name = resolve_map_engine(config, p_engine)
    if engine_name == "maplibre":
        # Must happen before the application object exists.
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
    app = QGuiApplication(sys.argv[:1])
    app.setOrganizationName("aalu")  # QML Settings: ~/.config/aalu/aalu-dashboard.conf
    app.setApplicationName("aalu-dashboard")
    if not config.map.cache_dir:
        cache = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        config = dataclasses.replace(
            config, map=dataclasses.replace(config.map, cache_dir=str(Path(cache) / "tiles")))

    proxy: TileProxy | None = None
    if config.map.proxy:
        proxy = TileProxy(config.map.tile_url, config.map.user_agent)
        config = dataclasses.replace(
            config, map=dataclasses.replace(config.map, tile_url=proxy.start()))

    core = VehicleCore(config)
    for item in args.sim:
        key, _, value = item.partition("=")
        core.scenario.set(key, value.lower() in ("1", "true", "yes", "on"))
    backend = Backend(core)
    backend.initial_panel = args.panel or ""
    map_server: MapServer | None = None
    if engine_name == "maplibre":
        map_server = MapServer(
            ROOT / "apps" / "dashboard" / "web", config.resolve(config.map.maps_dir),
            core.map_packs,
            "https://tile.openstreetmap.org/" if config.map.online_fallback else None,
            config.map.user_agent)
        backend.set_map_server(map_server.start() + "web/map.html", "maplibre")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("Vehicle", backend.vehicle)
    engine.rootContext().setContextProperty("Backend", backend)

    warnings: list[str] = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))

    windows = create_windows(engine, config, args.layout or config.screen_layout, args.only,
                             args.view, args.page)
    backend.start()
    if args.search:
        start_search(core, args.search, args.go)
    if args.gpx:
        QTimer.singleShot(1500, lambda: core.load_gpx(args.gpx, preview=not args.go))

    # Clean exit on SIGTERM (systemd) and Ctrl+C. A timer lets Python see signals.
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    tick = QTimer()
    tick.start(250)
    tick.timeout.connect(lambda: None)

    if args.quit_after:
        def finish() -> None:
            if args.screenshot_dir:
                out = Path(args.screenshot_dir)
                out.mkdir(parents=True, exist_ok=True)
                for name, w in windows.items():
                    quick = shiboken6.wrapInstance(shiboken6.getCppPointer(w)[0], QQuickWindow)
                    quick.grabWindow().save(str(out / f"{name}.png"))
            app.quit()
        QTimer.singleShot(int(args.quit_after * 1000), finish)

    code = app.exec()
    backend.stop()
    if proxy:
        proxy.stop()
    if map_server:
        map_server.stop()
    # Tear down QML before the context objects it references.
    for w in windows.values():
        shiboken6.delete(w)
    windows.clear()
    del engine
    for w in warnings:
        log.warning("QML: %s", w)
    return 1 if (code == 0 and warnings and args.quit_after) else code


if __name__ == "__main__":
    sys.exit(main())
