from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from cannonball_playgodot import PlayGodotClient

ConditionerState = dict[str, Any]


async def wait_for_describe(
    client: PlayGodotClient,
    automation_id: str,
    predicate: Callable[[dict[str, Any]], bool],
    failure: str,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Poll a described node until ``predicate`` holds on its full description.

    Bridge state converges over rendered frames, not wall-clock time, so a
    fixed sleep followed by a single sample couples the assertion to runner
    speed. Waiting on the observable transition changes no threshold: on
    timeout the wait fails with the last observed description, so a state that
    never converges still fails, now with its diagnosis attached.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        description = await client.describe(automation_id)
        if predicate(description):
            return description
        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail(f"{failure}; description={description}")
        await asyncio.sleep(0.02)


async def wait_for_conditioner(
    client: PlayGodotClient,
    predicate: Callable[[ConditionerState], bool],
    failure: str,
    timeout: float = 2.0,
) -> ConditionerState:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        state = (await client.describe("vehicle.input.conditioner"))["test_state"]
        if predicate(state):
            return state
        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail(f"{failure}; state={state}")
        await asyncio.sleep(0.02)


async def wait_for_key_conditioner(
    client: PlayGodotClient,
    *,
    key: str,
    raw_field: str,
    predicate: Callable[[ConditionerState], bool],
    failure: str,
    timeout: float = 2.0,
) -> ConditionerState:
    """Hold a key through focus transitions until its conditioned state is observed."""
    deadline = asyncio.get_running_loop().time() + timeout
    await client.request("input.key", {"key": key, "state": "press"})
    while True:
        state = (await client.describe("vehicle.input.conditioner"))["test_state"]
        if state["input_suppressed"] is True:
            await client.request("input.key", {"key": key, "state": "release"})
        elif state[raw_field] < 1:
            await client.request("input.key", {"key": key, "state": "press"})
        elif predicate(state):
            return state

        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail(f"{failure}; state={state}")
        await asyncio.sleep(0.02)
