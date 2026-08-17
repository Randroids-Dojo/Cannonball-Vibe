"""Tests for the capture idle precondition (ADR-0023 Q-022a, 2026-08-14).

`scripts/record_machine_state.py` decides whether a reference-performance capture
is admissible. It runs under this project's environment, so its tests live here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "record_machine_state.py"
_SPEC = importlib.util.spec_from_file_location("record_machine_state", _MODULE_PATH)
assert _SPEC and _SPEC.loader
record_machine_state = importlib.util.module_from_spec(_SPEC)
sys.modules["record_machine_state"] = record_machine_state
_SPEC.loader.exec_module(record_machine_state)

IDLE_GPU = "3, 2, 1800, 45, 60"
BUSY_GPU = "84, 41, 1900, 71, 260"
DESKTOP_CLIENTS = "1234, dwm.exe\n5678, explorer.exe"


def _during(rows: list[tuple[float, float, float]], tmp_path: Path) -> str:
    path = tmp_path / "during.csv"
    path.write_text(
        "".join(f"{seconds},{utilisation},{clients}\n" for seconds, utilisation, clients in rows),
        encoding="utf-8",
    )
    return str(path)


def _assess(
    gpu_before: str,
    clients_before: str,
    during_path: str | None,
    ceiling: float | None = None,
) -> dict:
    before = record_machine_state.parse_gpu(gpu_before)
    listed = record_machine_state.summarise_clients(clients_before)
    during = record_machine_state.summarise_during(
        record_machine_state.parse_during_samples(during_path),
        int(listed["count"]),
    )
    return record_machine_state.assess(before, listed, during, ceiling=ceiling)


def test_idle_capture_is_admissible(tmp_path: Path) -> None:
    during = _during([(0, 3, 3), (2, 78, 3), (4, 80, 3)], tmp_path)
    assessment = _assess(IDLE_GPU, DESKTOP_CLIENTS, during)
    assert assessment["contended"] is False
    assert assessment["reasons"] == []


def test_busy_gpu_before_the_capture_is_contended(tmp_path: Path) -> None:
    during = _during([(0, 80, 3)], tmp_path)
    assessment = _assess(BUSY_GPU, DESKTOP_CLIENTS, during)
    assert assessment["contended"] is True
    assert any("84% before the capture" in reason for reason in assessment["reasons"])


def test_memory_bandwidth_activity_alone_is_not_contention(tmp_path: Path) -> None:
    """An idle desktop compositor keeps utilization.memory in the mid teens.

    Gating on it refused every capture on a real interactive machine while saying
    nothing about whether another process was doing sustained GPU work.
    """
    during = _during([(0, 78, 3)], tmp_path)
    assessment = _assess("6, 16, 1800, 45, 60", DESKTOP_CLIENTS, during)
    assert assessment["contended"] is False


def test_client_arriving_mid_run_is_contended(tmp_path: Path) -> None:
    """The failure the bracketing samples missed: a client that comes and goes."""
    during = _during([(0, 78, 3), (2, 79, 3), (4, 95, 6), (6, 80, 3)], tmp_path)
    assessment = _assess(IDLE_GPU, DESKTOP_CLIENTS, during)
    assert assessment["contended"] is True
    assert any("appeared during the run" in reason for reason in assessment["reasons"])


def test_high_utilisation_during_the_run_is_not_contention(tmp_path: Path) -> None:
    """The capture is meant to load the GPU; only a new client is contention."""
    during = _during([(0, 99, 3), (2, 100, 3), (4, 100, 3)], tmp_path)
    assert _assess(IDLE_GPU, DESKTOP_CLIENTS, during)["contended"] is False


def test_unsampleable_gpu_is_contended_rather_than_assumed_idle(tmp_path: Path) -> None:
    during = _during([(0, 50, 3)], tmp_path)
    assessment = _assess("unavailable", DESKTOP_CLIENTS, during)
    assert assessment["contended"] is True
    assert any("could not be sampled" in reason for reason in assessment["reasons"])


def test_capture_process_already_running_is_contended(tmp_path: Path) -> None:
    during = _during([(0, 50, 3)], tmp_path)
    assessment = _assess(IDLE_GPU, "999, godot.exe\n1234, dwm.exe", during)
    assert assessment["contended"] is True
    assert any("already held a GPU context" in reason for reason in assessment["reasons"])


def test_missing_during_series_does_not_claim_a_new_client(tmp_path: Path) -> None:
    assessment = _assess(IDLE_GPU, DESKTOP_CLIENTS, str(tmp_path / "absent.csv"))
    assert assessment["contended"] is False


@pytest.mark.parametrize(
    "raw",
    [
        "1234, C:\\Users\\someone\\AppData\\Local\\Battle.net\\Battle.net.exe",
        "1234, /home/someone/.local/share/Steam/steam.exe",
    ],
)
def test_client_summary_keeps_no_identifying_detail(raw: str) -> None:
    """Capture evidence is committed publicly; it must not inventory the machine."""
    summary = record_machine_state.summarise_clients(raw)
    assert set(summary) == {"count", "includes_capture_process", "not_attributable_count"}
    assert summary["count"] == 1
    serialised = repr(summary)
    for fragment in ("Battle", "Steam", "someone", "Users", "home", ".exe"):
        assert fragment not in serialised


def test_idle_ceiling_is_a_declared_constant() -> None:
    """It gates admissibility, so a silent change to it should be visible in review."""
    assert record_machine_state.IDLE_UTILIZATION_CEILING_PERCENT == 10.0


def test_raised_ceiling_admits_a_busier_machine_and_says_so(tmp_path: Path) -> None:
    """Raising the ceiling is allowed, but the capture must declare it.

    A reference machine in use cannot reach the 10% default. The owner may still
    want a measurement, so the ceiling is overridable - but a capture taken above
    the default was not taken on an idle machine, and its own evidence has to say
    so or it will later be read as one that was.
    """
    during = _during([(0, 78, 3)], tmp_path)
    busy_desktop = "20, 18, 1800, 45, 60"

    assert _assess(busy_desktop, DESKTOP_CLIENTS, during)["contended"] is True

    relaxed = _assess(busy_desktop, DESKTOP_CLIENTS, during, ceiling=25.0)

    assert relaxed["contended"] is False
    assert relaxed["idle_ceiling_percent"] == 25.0
    assert relaxed["idle_ceiling_is_default"] is False
    assert "not taken on an idle machine" in relaxed["idle_ceiling_note"]


def test_default_ceiling_is_marked_as_the_default(tmp_path: Path) -> None:
    during = _during([(0, 78, 3)], tmp_path)
    assessment = _assess(IDLE_GPU, DESKTOP_CLIENTS, during)

    assert assessment["idle_ceiling_percent"] == 10.0
    assert assessment["idle_ceiling_is_default"] is True


def test_ceiling_override_is_read_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("CANNONBALL_IDLE_GPU_CEILING_PERCENT", "30")
    assert record_machine_state.idle_ceiling_percent() == 30.0
    monkeypatch.setenv("CANNONBALL_IDLE_GPU_CEILING_PERCENT", "not-a-number")
    with pytest.raises(ValueError, match="not a number"):
        record_machine_state.idle_ceiling_percent()
    monkeypatch.setenv("CANNONBALL_IDLE_GPU_CEILING_PERCENT", "150")
    with pytest.raises(ValueError, match="percentage"):
        record_machine_state.idle_ceiling_percent()
