from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "source",
    [
        'float ReadRaw() => Godot.Input.GetActionStrength("accelerate");',
        'float ReadRaw() => Input.GetAxis(GameInputMap.Left,\n "steer_right");',
    ],
)
def test_input_guard_catches_wrappers_inside_helpers(tmp_path: Path, source: str):
    (tmp_path / "Input.cs").write_text(source)
    failures = load_script("check_frame_allocations").scan(tmp_path)
    assert len(failures) == 1
    assert "StringName" in failures[0]


def test_input_guard_accepts_cached_handles_and_ignores_comments(tmp_path: Path):
    (tmp_path / "Input.cs").write_text(
        'static readonly StringName Accelerate = "accelerate";\n'
        '// Godot.Input.GetActionStrength("accelerate");\n'
        "float ReadRaw() => Godot.Input.GetActionStrength(Accelerate);"
    )
    assert load_script("check_frame_allocations").scan(tmp_path) == []


def test_capture_watchdog_preserves_engine_exit_code():
    watchdog = load_script("run_with_timeout")
    assert watchdog.run(5, [sys.executable, "-c", "raise SystemExit(7)"]) == 7


def test_capture_watchdog_terminates_a_stalled_engine():
    watchdog = load_script("run_with_timeout")
    assert watchdog.run(0.05, [sys.executable, "-c", "import time; time.sleep(30)"]) == 124
