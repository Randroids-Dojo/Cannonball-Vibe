from __future__ import annotations

from types import FunctionType

import pytest

from .input_support import wait_for_joy_conditioner


class _Polling:
    def __init__(self) -> None:
        self.now = 0.0

    def get_running_loop(self) -> _Polling:
        return self

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


class _Client:
    def __init__(self, states: list[dict]) -> None:
        self.states = iter(states)
        self.last: dict = {}
        self.values: list[float] = []

    async def request(self, method: str, params: dict) -> dict:
        assert method == "input.joypad_motion"
        assert params["axis"] == "trigger_right" and params["device"] == 3
        self.values.append(params["value"])
        return {}

    async def describe(self, automation_id: str) -> dict:
        assert automation_id == "vehicle.input.conditioner"
        self.last = next(self.states, self.last)
        return {"test_state": self.last.copy()}


def _state(raw: float = 0, conditioned: float = 0, *, suppressed=False, device=3) -> dict:
    return {"raw_throttle": raw, "conditioned_throttle": conditioned,
            "input_suppressed": suppressed, "active_controller_device": device}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("states", "expected_values"),
    [
        ([_state(1, 0.5)], [1]),
        ([_state(), _state(1), _state(1, 0.5)], [1, 1]),
        ([_state(1, 0.5, suppressed=True), _state(), _state(1, 0.5)], [1, 0, 1]),
    ],
    ids=["already-held", "cleared-during-startup", "requires-neutral-before-reapply"],
)
async def test_controller_setup_observes_held_input(states, expected_values) -> None:
    polling = _Polling()
    helper = FunctionType(wait_for_joy_conditioner.__code__,
                          {**wait_for_joy_conditioner.__globals__, "asyncio": polling})
    client = _Client(states)
    state = await helper(
        client, axis="trigger_right", value=1, device=3, raw_field="raw_throttle",
        predicate=lambda s: s["active_controller_device"] == 3 and s["conditioned_throttle"] > 0,
        failure="Controller throttle did not become active", timeout=2.0,
    )
    assert state["conditioned_throttle"] > 0 and state["input_suppressed"] is False
    assert client.values == expected_values
    assert polling.now < 2.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [_state(1, 0.5, suppressed=True), _state(1), _state(1, 0.5, device=2)],
    ids=["stuck-suppression", "no-conditioned-response", "wrong-controller"],
)
async def test_controller_setup_rejects_missing_precondition(state) -> None:
    polling = _Polling()
    helper = FunctionType(wait_for_joy_conditioner.__code__,
                          {**wait_for_joy_conditioner.__globals__, "asyncio": polling})
    client = _Client([state])
    with pytest.raises(pytest.fail.Exception, match="Controller throttle did not become active"):
        await helper(
            client, axis="trigger_right", value=1, device=3, raw_field="raw_throttle",
            predicate=lambda s: s["active_controller_device"] == 3
            and s["conditioned_throttle"] > 0,
            failure="Controller throttle did not become active", timeout=2.0,
        )
    assert 2.0 <= polling.now < 2.021
    assert client.values == ([1] + [0] * (len(client.values) - 1)
                             if state["input_suppressed"] else [1])
