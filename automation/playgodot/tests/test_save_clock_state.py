from __future__ import annotations

import copy
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType

import pytest

from . import input_support, test_endurance_sedan


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now


class _Asyncio:
    """Advance only the test's polling clock, without patching the event loop."""

    def __init__(self) -> None:
        self.clock = _Clock()

    def get_running_loop(self) -> _Clock:
        return self.clock

    async def sleep(self, seconds: float) -> None:
        self.clock.now += seconds


class _Client:
    def __init__(self, states: list[dict], path: Path, saved: float, replacement: float | None):
        self.states = copy.deepcopy(states)
        self.path = path
        self.saved = saved
        self.replacement = replacement
        self.last: dict | None = None
        self.describes = 0

    async def describe(self, automation_id: str) -> dict:
        assert automation_id == "run.session"
        self.describes += 1
        if self.states:
            self.last = self.states.pop(0)
        if self.replacement is not None and self.describes == 3:
            self.path.write_text(json.dumps({"run": {"elapsedSeconds": self.replacement}}))
        return {"test_state": copy.deepcopy(self.last)}

    async def request(self, method: str, params: dict) -> dict:
        assert method == "input.key"
        assert params in ({"key": "F5", "state": "press"}, {"key": "F5", "state": "release"})
        if params["state"] == "press":
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"run": {"elapsedSeconds": self.saved}}))
        return {}


def _implementation(legacy: bool, polling: _Asyncio):
    scope = {**vars(test_endurance_sedan), "asyncio": polling}
    scope["wait_for_describe"] = FunctionType(input_support.wait_for_describe.__code__, scope)
    for name in ("_key", "_clock_after", "_verify_selected_clock_and_save"):
        scope[name] = FunctionType(getattr(test_endurance_sedan, name).__code__, scope)
    if legacy:
        # A narrow historical negative control restores the actual a159 ordering.
        # It shares the real clock, selection and polling assertions with the
        # current function; no reports directory or frozen source file is needed.
        text = inspect.getsource(test_endurance_sedan._verify_selected_clock_and_save)
        replacements = {
            "            saved_bytes = save_path.read_bytes()\n"
            "            saved = json.loads(saved_bytes)":
            "            saved = json.loads(save_path.read_text())",
            '    save_read_barrier = (await client.describe("run.session"))["test_state"]\n'
            '    assert save_read_barrier["clock_ticks_msec"] >= after["clock_ticks_msec"]\n'
            '    following = await _clock_after(client, save_read_barrier["clock_ticks_msec"] + 1)':
            '    following = await _clock_after(client, after["clock_ticks_msec"] + 1)\n'
            '    assert saved["run"]["elapsedSeconds"] <= following["elapsed_seconds"] + 0.01\n'
            "    saved_bytes = save_path.read_bytes()",
            '                         "save_read_barrier": save_read_barrier,\n'
            '                         "following": following,\n': "",
        }
        for before, after in replacements.items():
            assert text.count(before) == 1, "Historical ordering mutation no longer matches"
            text = text.replace(before, after)
        tail = (
            '    (artifacts / "sedan-selection-clock-observations.json").write_text(\n'
            '        json.dumps(observations, indent=2) + "\\n",\n'
            "    )\n"
            '    assert saved["run"]["elapsedSeconds"] <= following["elapsed_seconds"] + 0.01\n'
        )
        assert text.count(tail) == 1
        text = text.replace(tail, "")
        exec(compile("from __future__ import annotations\n" + text, "<legacy-clock-order>", "exec"),
             scope)
    return scope["_verify_selected_clock_and_save"]


def _state(elapsed: float, ticks: int | None = None) -> dict:
    return {
        "selected_asset": "hero-gt", "elapsed_seconds": elapsed,
        "clock_ticks_msec": round(elapsed * 1000) + 6224 if ticks is None else ticks,
        "vehicle_position_x": -1.797, "vehicle_position_z": 0.00035,
    }


@dataclass(frozen=True)
class _Case:
    name: str
    states: list[dict]
    saved: float
    expected: tuple[str, str]
    replacement: float | None = None


# Elapsed values reproduce Mac a159's retained50.375/50.355 assertion. The
# subsequent cache samples/timestamps are declared synthetic event schedules.
_BEFORE = _state(49.144)
_AFTER = _state(50.160)
_STALE = _state(50.355)
_FRESH = _state(50.415)
_LATER = _state(50.455)
_CASES = [
    _Case("measured-stale", [_BEFORE, _AFTER, _STALE, _FRESH], 50.375,
          ("assertion", "passed")),
    _Case("already-fresh", [_BEFORE, _AFTER, _FRESH, _LATER], 50.375,
          ("passed", "passed")),
    _Case("repeated-stale", [_BEFORE, _AFTER, _STALE, _STALE, _STALE, _FRESH], 50.375,
          ("assertion", "passed")),
    _Case("frozen-cache", [_BEFORE, _AFTER, _STALE], 50.375,
          ("assertion", "deadline")),
    _Case("future-save", [_BEFORE, _AFTER, _STALE, _FRESH, _LATER], 51.375,
          ("assertion", "assertion")),
    _Case("stale-save", [_BEFORE, _AFTER, _STALE, _FRESH], 49.0,
          ("assertion", "assertion")),
    _Case("deducted-pause", [_BEFORE, _state(49.144, 56384), _STALE, _FRESH], 50.375,
          ("assertion", "assertion")),
    _Case("selection-teleport", [{**_BEFORE, "vehicle_position_x": 18.2}, _AFTER, _STALE],
          50.375, ("assertion", "assertion")),
    _Case("regressed-elapsed", [_BEFORE, _AFTER, _STALE, _state(50.1, 56700)], 50.375,
          ("assertion", "assertion")),
    _Case("replaced-file", [_BEFORE, _AFTER, _FRESH, _LATER], 50.375,
          ("passed", "passed"), replacement=90.0),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("legacy", [True, False], ids=["legacy", "current"])
async def test_save_clock_observation_schedule(case: _Case, legacy: bool, tmp_path: Path) -> None:
    polling = _Asyncio()
    verify = _implementation(legacy, polling)
    user = tmp_path / "user"
    client = _Client(case.states, user / "runs/suspended-run.json", case.saved, case.replacement)
    observations: list[dict] = []
    prior = {"elapsed_seconds": 28.703, "vehicle_position_x": -1.8, "vehicle_position_z": 0.0}
    expected = case.expected[0 if legacy else 1]
    if expected == "passed":
        await verify(client, "hero-gt", user, observations, tmp_path, prior)
    elif expected == "assertion":
        with pytest.raises(AssertionError):
            await verify(client, "hero-gt", user, observations, tmp_path, prior)
    else:
        with pytest.raises(pytest.fail.Exception, match="actual engine clock"):
            await verify(client, "hero-gt", user, observations, tmp_path, prior)
        assert polling.clock.now >= 10

    retained_path = tmp_path / "sedan-selection-hero-gt-save.json"
    if case.name == "replaced-file":
        retained = json.loads(retained_path.read_bytes())
        assert retained["run"]["elapsedSeconds"] == (90.0 if legacy else case.saved)
    if not legacy and case.name == "future-save":
        # Reject the first new timestamp; never wait for elapsed to catch up.
        assert client.describes == 4
        assert json.loads(retained_path.read_bytes())["run"]["elapsedSeconds"] == case.saved
        evidence = json.loads((tmp_path / "sedan-selection-clock-observations.json").read_bytes())
        assert evidence[-1]["save_read_barrier"]["elapsed_seconds"] == 50.355
        assert evidence[-1]["following"]["elapsed_seconds"] == 50.415
