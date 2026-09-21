from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path

import pytest

from cannonball_playgodot import PlayGodotProcess

REPO_ROOT = Path(__file__).resolve().parents[3]


def _route_package() -> Path:
    package_root = REPO_ROOT / ".tools/scenarios/official-corridor"
    pointer = json.loads((package_root / "current-package.json").read_text())
    return package_root / pointer["root_relative_path"]


def _artifacts(tmp_path: Path) -> Path:
    configured = os.environ.get("PLAYGODOT_ARTIFACT_DIR")
    directory = Path(configured) if configured else tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def _action(client, action: str) -> None:
    await client.request("input.action", {"action": action, "state": "press"})
    await asyncio.sleep(0.03)
    await client.request("input.action", {"action": action, "state": "release"})
    await asyncio.sleep(0.08)


async def _settle(
    client,
    node: str,
    predicate,
    timeout: float = 3.0,
    interval: float = 0.05,
    held_action: str | None = None,
) -> dict:
    """Poll ``node`` until ``predicate`` holds, then return that state.

    Camera blends and held-look motion converge over rendered frames, not wall-clock time.
    Sleeping a fixed interval and asserting immediately couples the assertion to runner
    speed. Polling changes no threshold: on timeout the last observed state is returned,
    so the caller's assertions still run and still fail if the camera never converges.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    state: dict = {}

    async def read_state() -> dict:
        # Native focus changes during startup can clear an injected action
        # after its acknowledgement. Reassert a continuous hold while waiting
        # for its camera response, within the same original deadline.
        if held_action is not None:
            await client.request(
                "input.action", {"action": held_action, "state": "press"}
            )
        return (await client.describe(node))["test_state"]

    remaining = deadline - loop.time()
    if remaining <= 0:
        return state
    try:
        state = await asyncio.wait_for(read_state(), remaining)
    except TimeoutError:
        return state

    while not predicate(state):
        remaining = deadline - loop.time()
        if remaining <= 0:
            return state
        try:
            await asyncio.wait_for(asyncio.sleep(interval), remaining)
        except TimeoutError:
            return state

        remaining = deadline - loop.time()
        if remaining <= 0:
            return state
        try:
            state = await asyncio.wait_for(read_state(), remaining)
        except TimeoutError:
            return state
    return state


@pytest.mark.asyncio
async def test_settle_bounds_a_delayed_initial_description() -> None:
    class DelayedClient:
        async def describe(self, _node: str) -> dict:
            await asyncio.sleep(0.2)
            return {"test_state": {"ready": False}}

    loop = asyncio.get_running_loop()
    started = loop.time()
    state = await _settle(
        DelayedClient(),
        "camera.chase.rig",
        lambda candidate: candidate.get("ready", False),
        timeout=0.05,
        interval=0.01,
    )
    elapsed = loop.time() - started

    assert state == {}
    assert elapsed < 0.15


@pytest.mark.asyncio
async def test_settle_restores_a_hold_cleared_after_acknowledgement() -> None:
    class FocusTransitionClient:
        presses = 0

        async def request(self, method: str, params: dict) -> None:
            assert method == "input.action"
            assert params == {"action": "look_behind", "state": "press"}
            self.presses += 1

        async def describe(self, _node: str) -> dict:
            # The first acknowledged press is cleared by a native focus event.
            held = self.presses > 1
            return {"test_state": {"rear_view_held": held, "rear_view_blend": int(held)}}

    client = FocusTransitionClient()
    state = await _settle(
        client,
        "camera.chase.rig",
        lambda s: s["rear_view_held"] and s["rear_view_blend"] > 0.9,
        interval=0.005,
        held_action="look_behind",
    )
    assert state == {"rear_view_held": True, "rear_view_blend": 1}
    assert client.presses == 2


@pytest.mark.asyncio
async def test_settle_bounds_a_delayed_hold_request() -> None:
    class DelayedInputClient:
        async def request(self, _method: str, _params: dict) -> None:
            await asyncio.sleep(0.2)

        async def describe(self, _node: str) -> dict:
            pytest.fail("An expired hold request must not start a description")

    loop = asyncio.get_running_loop()
    started = loop.time()
    state = await _settle(
        DelayedInputClient(),
        "camera.chase.rig",
        lambda s: s.get("rear_view_held", False),
        timeout=0.05,
        held_action="look_behind",
    )
    assert state == {}
    assert loop.time() - started < 0.15


def _assert_completed_chase_cast(state: dict) -> None:
    """Check one completed native cast; current requested length may have changed."""
    assert state["spring_cast_ready"] is True, state
    for name in (
        "spring_observation_epoch",
        "spring_cast_epoch",
        "spring_cast_generation",
        "spring_cast_physics_frame",
        "spring_observation_physics_frame",
    ):
        assert type(state[name]) is int and state[name] >= 0, state
    assert state["spring_cast_generation"] > 0, state
    assert state["spring_cast_epoch"] > 0, state
    assert state["spring_cast_epoch"] == state["spring_observation_epoch"], state
    assert state["spring_cast_physics_frame"] <= state["spring_observation_physics_frame"], state
    instance = state["spring_cast_arm_instance_id"]
    assert isinstance(instance, str) and instance.isascii() and instance.isdigit(), state
    assert int(instance) > 0 and instance == state["spring_arm_instance_id"], state
    request, hit, compression = (
        state["spring_cast_request_m"],
        state["spring_cast_hit_m"],
        state["spring_cast_compression_m"],
    )
    assert all(
        type(value) in (int, float) and math.isfinite(value)
        for value in (request, hit, compression)
    ), state
    assert 0 <= hit <= request, state
    assert compression == max(0, request - hit), state

def _assert_attached_and_level(state: dict) -> None:
    assert state["target_valid"] is True
    assert state["top_level"] is True
    assert state["inherits_vehicle_rotation"] is False
    assert state["target_distance_m"] < 15
    assert abs(state["horizon_roll_degrees"]) < 0.01


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_camera_handling_survives_pause_device_reset_and_mode_transitions(
    tmp_path: Path,
) -> None:
    artifacts = _artifacts(tmp_path)
    # The production rig's cockpit contract is checked by the headless
    # camera-handling scenario on the M0 path; this test runs the graybox car
    # like the rest of the suite, because the production rig drew too few
    # frames on the software renderers for the rear-view settle window
    # (Q-042: 0.85 and 0.84 of the 0.9 bound on macOS).
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input", "screenshot"),
        request_timeout=30.0,
        transcript=artifacts / "camera-handling.jsonl",
        log_path=artifacts / "camera-handling-godot.log",
    )
    async with process as client:
        chase = await _settle(
            client, "camera.chase.rig", lambda s: s.get("spring_cast_ready") is True
        )
        _assert_attached_and_level(chase)
        assert chase["active"] is True
        _assert_completed_chase_cast(chase)
        assert chase["collision_compression_m"] >= 0

        chase_rear = await _settle(
            client,
            "camera.chase.rig",
            lambda s: s["rear_view_held"] and s["rear_view_blend"] > 0.9,
            held_action="look_behind",
        )
        assert chase_rear["rear_view_held"] is True, chase_rear
        assert chase_rear["rear_view_blend"] > 0.9
        assert chase_rear["rear_view_yaw_degrees"] > 160
        await client.request(
            "input.action", {"action": "look_behind", "state": "release"}
        )
        chase_forward = await _settle(
            client, "camera.chase.rig", lambda s: s["rear_view_blend"] < 0.02
        )
        assert chase_forward["rear_view_held"] is False
        assert chase_forward["rear_view_blend"] < 0.02
        assert chase_forward["rear_view_yaw_degrees"] < 4

        await _action(client, "toggle_camera")
        cockpit = await _settle(
            client, "camera.cockpit.view", lambda s: s["active"] is True
        )
        assert cockpit["active"] is True
        assert cockpit["vehicle_local"] is True
        assert abs(cockpit["horizon_roll_degrees"]) < 10
        assert cockpit["camera_offset_x"] == 0
        assert cockpit["camera_offset_y"] == 0
        assert cockpit["camera_offset_z"] == 0
        assert cockpit["near_clip_m"] == pytest.approx(0.05)
        # Cockpit exclusion names, exterior-layer cull masks and sourced
        # texture binding are the production rig's contract; the headless
        # camera-handling scenario asserts them on every M0 run.
        cockpit_capture = await client.screenshot(artifacts / "cockpit-forward.png")
        assert cockpit_capture["bytes"] > 0
        assert cockpit_capture["width"] >= 960
        assert cockpit_capture["height"] >= 540

        await client.request(
            "input.action", {"action": "camera_look_right", "state": "press"}
        )
        looking = await _settle(
            client, "camera.cockpit.view", lambda s: s["look_yaw_degrees"] > 1
        )
        assert 1 < looking["look_yaw_degrees"] <= looking["maximum_look_yaw_degrees"]
        await client.request(
            "input.action", {"action": "camera_look_right", "state": "release"}
        )

        await client.request("input.action", {"action": "reverse", "state": "press"})
        cockpit_rear = await _settle(
            client,
            "camera.cockpit.view",
            lambda s: s["rear_view_held"] and s["rear_view_blend"] > 0.99,
            held_action="look_behind",
        )
        reversing = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert reversing["raw_reverse"] == 1
        assert cockpit_rear["rear_view_held"] is True
        assert cockpit_rear["rear_view_blend"] > 0.99
        assert abs(cockpit_rear["displayed_yaw_degrees"]) > 170

        await _action(client, "toggle_camera")
        switched_rear = await _settle(
            client, "camera.chase.rig", lambda s: s["active"] is True
        )
        assert switched_rear["active"] is True
        assert switched_rear["rear_view_held"] is True
        assert switched_rear["rear_view_yaw_degrees"] > 160
        await _action(client, "toggle_camera")
        cockpit_returned_active = await _settle(
            client, "camera.cockpit.view", lambda s: s["active"] is True
        )
        assert cockpit_returned_active["active"] is True

        await client.request(
            "input.action", {"action": "look_behind", "state": "release"}
        )
        await client.request("input.action", {"action": "reverse", "state": "release"})
        cockpit_returned = await _settle(
            client, "camera.cockpit.view", lambda s: abs(s["rear_view_blend"]) <= 0.01
        )
        assert cockpit_returned["rear_view_held"] is False
        assert cockpit_returned["rear_view_blend"] == pytest.approx(0, abs=0.01)
        assert abs(cockpit_returned["displayed_yaw_degrees"]) < 20

        await client.request(
            "input.action", {"action": "camera_look_left", "state": "press"}
        )
        left_look = await _settle(
            client, "camera.cockpit.view", lambda s: s["look_yaw_degrees"] < 0
        )
        assert left_look["look_yaw_degrees"] < 0
        await client.request(
            "input.action", {"action": "camera_look_left", "state": "release"}
        )

        await client.request("input.key", {"key": "Escape", "state": "press"})
        await client.request("input.key", {"key": "Escape", "state": "release"})
        menu = await _settle(
            client, "menu.driver.root", lambda s: s["simulation_paused"] is True
        )
        assert menu["simulation_paused"] is True
        assert (await client.describe("camera.cockpit.view"))["test_state"]["active"] is True

        await client.request("input.click", {"automation_id": "menu.driver.resume"})
        await client.request(
            "input.joypad_motion", {"axis": "left_x", "value": 0.6, "device": 2}
        )
        await asyncio.sleep(0.08)
        assert (await client.describe("camera.cockpit.view"))["test_state"]["active"] is True
        await client.request(
            "input.joypad_motion", {"axis": "left_x", "value": 0, "device": 2}
        )

        await _action(client, "toggle_camera")
        await _action(client, "reset_vehicle")
        chase = await _settle(
            client,
            "camera.chase.rig",
            lambda s: (
                s["active"] is True
                and s["target_valid"] is True
                and s["target_distance_m"] < 15
                and abs(s["horizon_roll_degrees"]) < 0.01
                and s.get("spring_cast_ready") is True
            ),
        )
        _assert_attached_and_level(chase)
        assert chase["active"] is True
        _assert_completed_chase_cast(chase)

        screenshot = await client.screenshot(artifacts / "camera-handling-final.png")
        assert screenshot["bytes"] > 0
        assert screenshot["width"] >= 960
        assert screenshot["height"] >= 540
