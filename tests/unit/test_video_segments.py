import os
from datetime import datetime

import pytest

from aalu.video.segments import SegmentStore

NOW = datetime(2026, 10, 23, 18, 0, 0).timestamp()


def write(path, size=1000, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def store(tmp_path):
    return SegmentStore(tmp_path / "dc", wall_clock=lambda: NOW)


def test_finalize_names_by_start_time(store):
    seg_file = write(store.incoming("front") / "seg_00000.mkv")
    seg = store.finalize("front", seg_file, started_at=NOW - 60)
    assert seg.path == store.root / "front" / "2026-10-23" / "front_20261023-175900.mkv"
    assert not seg_file.exists()


def test_finalize_without_valid_clock_does_not_invent_a_date(store):
    seg = store.finalize("rear", write(store.incoming("rear") / "seg_00000.mkv"), started_at=12.0)
    assert seg.path.parent.name == "noclock" and "1970" not in seg.path.name


def test_finalize_drops_empty_files_and_avoids_name_collisions(store):
    assert store.finalize("front", write(store.incoming("front") / "seg_0.mkv", 0), NOW) is None
    a = store.finalize("front", write(store.incoming("front") / "seg_1.mkv"), NOW)
    b = store.finalize("front", write(store.incoming("front") / "seg_2.mkv"), NOW)
    assert a.path != b.path and a.path.exists() and b.path.exists()


def test_retention_deletes_older_than_24h_but_never_protected(store):
    old = write(store.root / "front" / "2026-10-22" / "front_old.mkv", mtime=NOW - 25 * 3600)
    recent = write(store.root / "front" / "2026-10-23" / "front_new.mkv", mtime=NOW - 3600)
    prot = write(store.root / "protected" / "front" / "front_saved.mkv", mtime=NOW - 99 * 3600)
    deleted = store.enforce_retention(24, min_free_pct=0, free_pct=lambda: 50.0)
    assert deleted == [old]
    assert recent.exists() and prot.exists()
    assert not (store.root / "front" / "2026-10-22").exists()  # empty day folder removed


def test_retention_frees_space_oldest_first(store):
    files = [write(store.root / "rear" / "2026-10-23" / f"r{i}.mkv", mtime=NOW - 3600 + i)
             for i in range(5)]
    free = {"pct": 5.0}

    def free_pct():
        free["pct"] += 2.0  # each deletion frees 2 %
        return free["pct"] - 2.0

    deleted = store.enforce_retention(24, min_free_pct=10.0, free_pct=free_pct)
    assert deleted == files[:3]


def test_retention_keeps_segments_from_the_future(store):
    future = write(store.root / "front" / "2026-10-24" / "f.mkv", mtime=NOW + 3600)
    assert store.enforce_retention(24, 0, free_pct=lambda: 50.0) == []
    assert future.exists()


def test_protect_moves_out_of_retention(store):
    seg = store.finalize("front", write(store.incoming("front") / "seg_0.mkv"), NOW)
    target = store.protect(seg)
    assert target.parent == store.root / "protected" / "front"
    assert [s.path for s in store.segments(protected=True)] == [target]
    assert store.segments() == []
    assert store.protected_bytes() == 1000
