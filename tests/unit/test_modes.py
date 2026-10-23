import pytest

from aalu.core.modes import ModeEvent, ModeMachine, VehicleMode

M, E = VehicleMode, ModeEvent


@pytest.mark.parametrize(
    ("start", "event", "expected"),
    [
        (M.STANDBY, E.ACC_ON, M.DRIVE),
        (M.STANDBY, E.USER_WAKE, M.CAMP),
        (M.CAMP, E.ACC_ON, M.DRIVE),
        (M.CAMP, E.IDLE_TIMEOUT, M.STANDBY),
        (M.DRIVE, E.ACC_OFF, M.CAMP),
        (M.CAMP, E.SHUTDOWN_REQUEST, M.SHUTDOWN),
        (M.DRIVE, E.POWER_FAIL, M.SHUTDOWN),
        (M.CAMP, E.FAULT, M.FAULT),
    ],
)
def test_transitions(start, event, expected):
    m = ModeMachine(initial=start)
    m.handle(event)
    assert m.mode is expected


def test_no_shutdown_request_while_driving():
    m = ModeMachine(initial=M.DRIVE)
    assert m.handle(E.SHUTDOWN_REQUEST) is None
    assert m.mode is M.DRIVE


def test_drive_ignores_idle_timeout():
    m = ModeMachine(initial=M.DRIVE)
    assert m.handle(E.IDLE_TIMEOUT) is None


def test_shutdown_is_terminal():
    m = ModeMachine(initial=M.CAMP)
    m.handle(E.POWER_FAIL)
    for event in E:
        m.handle(event)
    assert m.mode is M.SHUTDOWN


def test_fault_clears_to_drive_or_camp_depending_on_acc():
    m = ModeMachine(initial=M.STANDBY)
    m.handle(E.ACC_ON)
    m.handle(E.FAULT)
    assert m.handle(E.ACC_ON) is None  # stays in FAULT, but ACC is tracked
    m.handle(E.FAULT_CLEARED)
    assert m.mode is M.DRIVE

    m.handle(E.FAULT)
    m.handle(E.ACC_OFF)
    m.handle(E.FAULT_CLEARED)
    assert m.mode is M.CAMP


def test_set_acc_emits_only_edges():
    transitions = []
    m = ModeMachine(initial=M.CAMP, on_transition=transitions.append)
    m.set_acc(True)
    m.set_acc(True)
    m.set_acc(False)
    assert [(t.previous, t.current) for t in transitions] == [(M.CAMP, M.DRIVE), (M.DRIVE, M.CAMP)]
