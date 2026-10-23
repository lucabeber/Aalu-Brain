"""Shared, mutable simulation scenario for fake adapters (fault injection).

Fields are plain bools written from the UI thread and read from adapter
threads; single attribute assignment is atomic in CPython, which is enough here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class Scenario:
    gnss_connected: bool = True
    gnss_fix: bool = True
    victron_connected: bool = True
    low_soc: bool = False
    phone_connected: bool = True
    mcu_connected: bool = True
    acc_on: bool = True
    engine_running: bool = True  # alternator charging (only with ACC on)
    sunny: bool = True
    reverse: bool = False

    def set(self, key: str, value: bool) -> None:
        if key not in {f.name for f in fields(self)}:
            raise KeyError(key)
        setattr(self, key, bool(value))

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)
