"""NmeaSerialAdapter against a pseudo-terminal standing in for the USB/UART receiver."""

import os
import pty
import queue
import time

import pytest

from aalu.adapters.gps.serial_nmea import NmeaReplayAdapter, NmeaSerialAdapter
from aalu.core.models import DataQuality, GnssFix
from conftest import FIXTURES

pytest.importorskip("serial")


def test_serial_adapter_reads_fix_from_pty():
    master, slave = pty.openpty()
    received: queue.Queue = queue.Queue()
    adapter = NmeaSerialAdapter(os.ttyname(slave), 115200)
    adapter.start(received.put)
    try:
        time.sleep(0.3)  # let the adapter open the port
        os.write(master, (FIXTURES / "nmea" / "drive_fix.nmea").read_bytes())
        reading = received.get(timeout=5)
        assert reading.quality is DataQuality.VALID
        assert reading.fix is GnssFix.FIX_3D
        assert reading.lat == pytest.approx(46.0679, abs=1e-3)
    finally:
        adapter.stop()
        os.close(master)
        os.close(slave)


def test_serial_adapter_survives_missing_port():
    received: queue.Queue = queue.Queue()
    adapter = NmeaSerialAdapter("/dev/does-not-exist", 115200)
    adapter.start(received.put)
    time.sleep(0.2)
    adapter.stop()  # retries quietly, never raises, never publishes
    assert received.empty()


def test_replay_adapter_marks_data_simulated():
    received: queue.Queue = queue.Queue()
    adapter = NmeaReplayAdapter(FIXTURES / "nmea" / "drive_fix.nmea", epoch_s=0.01)
    adapter.start(received.put)
    try:
        reading = received.get(timeout=5)
    finally:
        adapter.stop()
    assert reading.quality is DataQuality.SIMULATED and reading.fix is GnssFix.FIX_3D
