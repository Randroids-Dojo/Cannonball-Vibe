from __future__ import annotations

import asyncio
import json
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
) -> dict:
    """Poll ``node`` until ``predicate`` holds, then return that state.

    Camera blends and held-look motion converge over rendered frames, not wall-clock time.
    Sleeping a fixed interval and asserting immediately couples the assertion to runner
    speed. Polling changes no threshold: on timeout the last observed state is returned,
    so the caller's assertions still run and still fail if the camera never converges.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    state = (await client.describe(node))["test_state"]
    while not predicate(state) and loop.time() < deadline:
        await asyncio.sleep(interval)
        state = (await client.describe(node))["test_state"]
    return state


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
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input", "screenshot"),
        request_timeout=30.0,
        transcript=artifacts / "camera-handling.jsonl",
        log_path=artifacts / "camera-handling-godot.log",
    )
    async with process as client:
        chase = (await client.describe("camera.chase.rig"))["test_state"]
        _assert_attached_and_level(chase)
        assert chase["active"] is True
        assert chase["spring_hit_length_m"] <= chase["spring_length_m"]
        assert chase["collision_compression_m"] >= 0

        await client.request(
            "input.action", {"action": "look_behind", "state": "press"}
        )
        chase_rear = await _settle(
            client, "camera.chase.rig", lambda s: s["rear_view_blend"] > 0.9
        )
        assert chase_rear["rear_view_held"] is True
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
        cockpit = (await client.describe("camera.cockpit.view"))["test_state"]
        assert cockpit["active"] is True
        assert cockpit["vehicle_local"] is True
        assert abs(cockpit["horizon_roll_degrees"]) < 10
        assert cockpit["camera_offset_x"] == 0
        assert cockpit["camera_offset_y"] == 0
        assert cockpit["camera_offset_z"] == 0
        assert cockpit["near_clip_m"] == pytest.approx(0.05)
        visual = (await client.describe("vehicle.hero-gt.visual-rig"))["test_state"]
        assert visual["cockpit_excluded_mesh_count"] == 3
        assert visual["chase_exterior_geometry_visible"] is True
        exterior_layer = visual["cockpit_exterior_layer"]
        assert cockpit["cull_mask"] & exterior_layer == 0
        configured_chase = (await client.describe("camera.chase.rig"))["test_state"]
        assert configured_chase["cull_mask"] & exterior_layer == exterior_layer
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
        await client.request(
            "input.action", {"action": "look_behind", "state": "press"}
        )
        cockpit_rear = await _settle(
            client, "camera.cockpit.view", lambda s: s["rear_view_blend"] > 0.99
        )
        reversing = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert reversing["raw_reverse"] == 1
        assert cockpit_rear["rear_view_held"] is True
        assert cockpit_rear["rear_view_blend"] > 0.99
        assert abs(cockpit_rear["displayed_yaw_degrees"]) > 170
        assert cockpit_rear["look_yaw_degrees"] > 0

        await _action(client, "toggle_camera")
        switched_rear = (await client.describe("camera.chase.rig"))["test_state"]
        assert switched_rear["active"] is True
        assert switched_rear["rear_view_held"] is True
        assert switched_rear["rear_view_yaw_degrees"] > 160
        await _action(client, "toggle_camera")
        assert (await client.describe("camera.cockpit.view"))["test_state"]["active"] is True

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
        await asyncio.sleep(0.05)
        menu = await client.describe("menu.driver.root")
        assert menu["test_state"]["simulation_paused"] is True
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
        chase = (await client.describe("camera.chase.rig"))["test_state"]
        _assert_attached_and_level(chase)
        assert chase["active"] is True

        screenshot = await client.screenshot(artifacts / "camera-handling-final.png")
        assert screenshot["bytes"] > 0
        assert screenshot["width"] >= 960
        assert screenshot["height"] >= 540
