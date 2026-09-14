from __future__ import annotations

import copy

import pytest

from .shutdown_support import assert_clean_owned_shutdown


def _completed() -> dict:
    return {
        "status": "passed", "exit_status": 0, "output_eof": True,
        "quit_requested": True, "quit_acknowledged": True,
        "fallback": [], "diagnostics": [], "bookkeeping_completed": True,
        "unfinished_operations": 0, "total_budget_seconds": 8.0,
        "phase_seconds": [5.0, 1.0, 1.0, 1.0], "elapsed_seconds": 4.4,
        "connection_turnover_retries": 1,
        "phase_errors": [{"phase": "session-close", "type": "TimeoutError"}],
        "quit_cleanup": {"held_inputs_before": 0, "held_inputs_after": 0,
                         "pending_waits_before": 0, "pending_waits_after": 0},
    }


@pytest.mark.parametrize("recovered", [False, True])
def test_complete_owned_exit_accepts_only_recorded_recovery(recovered: bool) -> None:
    result = _completed()
    if not recovered:
        result.update(phase_errors=[], connection_turnover_retries=0)
    before = copy.deepcopy(result)
    assert_clean_owned_shutdown(result)
    assert result == before


@pytest.mark.parametrize(("key", "value"), [
    ("status", "failed"), ("exit_status", 1), ("exit_status", False),
    ("output_eof", False), ("quit_requested", False), ("quit_acknowledged", False),
    ("fallback", ["terminate"]), ("diagnostics", [{"text": "native leak"}]),
    ("bookkeeping_completed", False), ("unfinished_operations", 1),
    ("total_budget_seconds", 9), ("phase_seconds", [6, 1, 1, 1]),
    ("elapsed_seconds", 8.000001), ("elapsed_seconds", float("nan")),
    ("elapsed_seconds", -1), ("connection_turnover_retries", -1),
    ("phase_errors", [{"phase": "session-quit", "type": "TimeoutError"}]),
    ("phase_errors", [{"phase": "session-close", "type": "RuntimeError"}]),
    ("phase_errors", [{"phase": "bookkeeping", "type": "OSError"}]),
    ("phase_errors", [{"phase": "session-close", "type": "TimeoutError"}] * 2),
    ("quit_cleanup", None),
    ("quit_cleanup", {"held_inputs_before": 0, "held_inputs_after": 1,
                      "pending_waits_before": 0, "pending_waits_after": 0}),
    ("quit_cleanup", {"held_inputs_before": 0, "held_inputs_after": 0,
                      "pending_waits_before": 0, "pending_waits_after": 1}),
])
def test_recovered_connection_does_not_excuse_incomplete_exit(key: str, value: object) -> None:
    result = _completed()
    result[key] = value
    with pytest.raises(AssertionError):
        assert_clean_owned_shutdown(result)


def test_recovery_rejects_missing_quit_acknowledgement() -> None:
    result = _completed()
    del result["quit_acknowledged"]
    with pytest.raises(KeyError):
        assert_clean_owned_shutdown(result)
