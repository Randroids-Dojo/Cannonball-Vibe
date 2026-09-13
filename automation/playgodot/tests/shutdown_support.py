"""Assertions for completed ordinary owned-process shutdown in native tests."""

from __future__ import annotations

import math


def assert_clean_owned_shutdown(result: dict | None) -> None:
    """Permit the launcher's recorded, recovered initial connection timeout.

    The ordinary connection has only one second to close. Its timeout may
    recover through the separately authenticated quit within the unchanged
    deadline. Keep that row and retry count in evidence; never excuse an
    unacknowledged quit, fallback, incomplete cleanup or native diagnostic.
    """
    assert result is not None and result["status"] == "passed"
    assert type(result["exit_status"]) is int and result["exit_status"] == 0
    assert result["output_eof"] is True
    assert result["quit_requested"] is True and result["quit_acknowledged"] is True
    assert result["fallback"] == [] and result["diagnostics"] == []
    assert result["bookkeeping_completed"] is True
    assert type(result["unfinished_operations"]) is int and result["unfinished_operations"] == 0
    assert result["total_budget_seconds"] == 8.0
    assert result["phase_seconds"] == [5.0, 1.0, 1.0, 1.0]
    elapsed = result["elapsed_seconds"]
    assert type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 8.0
    retries = result["connection_turnover_retries"]
    assert type(retries) is int and retries >= 0
    assert result["phase_errors"] in (
        [], [{"phase": "session-close", "type": "TimeoutError"}],
    )
    cleanup = result["quit_cleanup"]
    assert isinstance(cleanup, dict) and set(cleanup) == {
        "held_inputs_before", "held_inputs_after", "pending_waits_before", "pending_waits_after",
    }
    assert all(type(value) is int and value >= 0 for value in cleanup.values())
    assert cleanup["held_inputs_after"] == 0 and cleanup["pending_waits_after"] == 0
