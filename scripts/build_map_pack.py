#!/usr/bin/env python3
"""Build an offline map pack. Needs Internet and the "maps" extra (pip install -e .[maps]).

    scripts/build_map_pack.py trentino-alto-adige
    scripts/build_map_pack.py italy --maps-dir /media/ssd/aalu-data/maps
    scripts/build_map_pack.py my-area --pbf-url https://.../area-latest.osm.pbf
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aalu.maps.build import REGIONS, build_pack  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("region", help=f"one of: {', '.join(REGIONS)} (or any name with --pbf-url)")
    p.add_argument("--maps-dir", default=str(ROOT / "data" / "maps"))
    p.add_argument("--pbf-url", help="OSM extract to use instead of the known region URL")
    p.add_argument("--max-zoom", type=int, default=15, help="highest map zoom stored (default 15)")
    p.add_argument("--force", action="store_true", help="rebuild every step")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    build_pack(args.region, Path(args.maps_dir).expanduser(), args.pbf_url, args.force,
               args.max_zoom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
