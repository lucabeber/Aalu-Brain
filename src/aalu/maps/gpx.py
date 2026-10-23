"""Minimal GPX 1.1 reading and writing (tracks, routes, waypoints). Standard library only.

Reading is tolerant: GPX 1.0 and 1.1, any namespace prefix, missing elevation/time.
Python's expat parser refuses entity-expansion bombs, so user files are safe to open.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

GPX_NS = "http://www.topografix.com/GPX/1/1"


@dataclass
class GpxPoint:
    lat: float
    lon: float
    ele: float | None = None
    time: datetime | None = None


@dataclass
class GpxData:
    name: str = ""
    description: str = ""
    time: datetime | None = None
    tracks: list[list[GpxPoint]] = field(default_factory=list)  # one list per segment
    routes: list[list[GpxPoint]] = field(default_factory=list)
    waypoints: list[tuple[GpxPoint, str]] = field(default_factory=list)

    def all_points(self) -> list[GpxPoint]:
        """Track points if present, otherwise route points (planner exports use <rte>)."""
        segments = self.tracks or self.routes
        return [p for seg in segments for p in seg]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _point(el: ET.Element) -> GpxPoint | None:
    try:
        lat, lon = float(el.attrib["lat"]), float(el.attrib["lon"])
    except (KeyError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    ele = time = None
    for child in el:
        tag = _local(child.tag)
        if tag == "ele":
            try:
                ele = float(child.text or "")
            except ValueError:
                ele = None
        elif tag == "time":
            time = _time(child.text)
    return GpxPoint(lat, lon, ele, time)


def _child_text(el: ET.Element, name: str) -> str:
    for child in el:
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def read_gpx(path: Path) -> GpxData:
    root = ET.parse(path).getroot()
    if _local(root.tag) != "gpx":
        raise ValueError(f"{path.name}: not a GPX file")
    data = GpxData()
    for el in root:
        tag = _local(el.tag)
        if tag == "metadata":
            data.name = data.name or _child_text(el, "name")
            data.description = _child_text(el, "desc")
            data.time = _time(_child_text(el, "time"))
        elif tag == "trk":
            data.name = data.name or _child_text(el, "name")
            for seg in el:
                if _local(seg.tag) == "trkseg":
                    pts = [p for p in (_point(x) for x in seg if _local(x.tag) == "trkpt") if p]
                    if pts:
                        data.tracks.append(pts)
        elif tag == "rte":
            data.name = data.name or _child_text(el, "name")
            pts = [p for p in (_point(x) for x in el if _local(x.tag) == "rtept") if p]
            if pts:
                data.routes.append(pts)
        elif tag == "wpt":
            p = _point(el)
            if p:
                data.waypoints.append((p, _child_text(el, "name")))
    if data.time is None:
        first = next((p.time for p in data.all_points() if p.time), None)
        data.time = first
    return data


def write_gpx(path: Path, name: str, tracks: Iterable[Sequence[GpxPoint]] = (),
              waypoints: Iterable[tuple[GpxPoint, str]] = (), description: str = "",
              time: datetime | None = None) -> None:
    """Atomic write (temporary file + rename): a power cut never leaves half a file."""
    ET.register_namespace("", GPX_NS)
    ns = "{" + GPX_NS + "}"
    gpx = ET.Element(ns + "gpx", {"version": "1.1", "creator": "AALU dashboard"})
    meta = ET.SubElement(gpx, ns + "metadata")
    ET.SubElement(meta, ns + "name").text = name
    if description:
        ET.SubElement(meta, ns + "desc").text = description
    if time:
        ET.SubElement(meta, ns + "time").text = time.isoformat().replace("+00:00", "Z")

    def add_point(parent: ET.Element, tag: str, p: GpxPoint) -> ET.Element:
        el = ET.SubElement(parent, ns + tag, {"lat": f"{p.lat:.7f}", "lon": f"{p.lon:.7f}"})
        if p.ele is not None:
            ET.SubElement(el, ns + "ele").text = f"{p.ele:.1f}"
        if p.time is not None:
            ET.SubElement(el, ns + "time").text = p.time.isoformat().replace("+00:00", "Z")
        return el

    for p, wname in waypoints:
        ET.SubElement(add_point(gpx, "wpt", p), ns + "name").text = wname
    for seg in tracks:
        trk = ET.SubElement(gpx, ns + "trk")
        ET.SubElement(trk, ns + "name").text = name
        trkseg = ET.SubElement(trk, ns + "trkseg")
        for p in seg:
            add_point(trkseg, "trkpt", p)
    tmp = path.with_suffix(path.suffix + ".tmp")
    ET.ElementTree(gpx).write(tmp, encoding="utf-8", xml_declaration=True)
    tmp.replace(path)
