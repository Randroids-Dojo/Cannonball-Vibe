from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from cannonball_playgodot import PlayGodotProcess

REPO_ROOT = Path(__file__).resolve().parents[3]


def _route_package() -> Path:
    package_root = REPO_ROOT / ".tools/scenarios/representative-corridor"
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


def _assert_attached_and_level(state: dict) -> None:
    assert state["target_valid"] is True
    assert state["top_level"] is True
    assert state["inherits_vehicle_rotation"] is False
    assert state["target_distance_m"] < 15
    assert state["horizon_roll_degrees"] < 0.01


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

        await _action(client, "toggle_camera")
        cockpit = (await client.describe("camera.cockpit.view"))["test_state"]
        assert cockpit["active"] is True
        assert cockpit["vehicle_local"] is True
        assert abs(cockpit["horizon_roll_degrees"]) < 10

        await client.request(
            "input.action", {"action": "camera_look_right", "state": "press"}
        )
        await asyncio.sleep(0.12)
        looking = (await client.describe("camera.cockpit.view"))["test_state"]
        assert 1 < looking["look_yaw_degrees"] <= looking["maximum_look_yaw_degrees"]
        await client.request(
            "input.action", {"action": "camera_look_right", "state": "release"}
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
