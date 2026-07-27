from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from cannonball_playgodot import PlayGodotClient

ConditionerState = dict[str, Any]


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
