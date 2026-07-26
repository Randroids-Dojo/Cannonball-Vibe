from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from cannonball_playgodot import PlayGodotProcess

REPO_ROOT = Path(__file__).resolve().parents[3]
REQUESTED_PROFILES = set(
    filter(None, os.environ.get("CANNONBALL_DRIVING_PROFILES", "all").split(","))
)
pytestmark = pytest.mark.skipif(
    "all" not in REQUESTED_PROFILES and "balanced" not in REQUESTED_PROFILES,
    reason="Live driving scenarios currently exercise the Balanced profile",
)


def _route_package() -> Path:
    package_root = REPO_ROOT / ".tools/scenarios/official-corridor"
    pointer = json.loads((package_root / "current-package.json").read_text())
    return package_root / pointer["root_relative_path"]


def _artifacts(tmp_path: Path) -> Path:
    configured = os.environ.get("PLAYGODOT_ARTIFACT_DIR")
    directory = Path(configured) if configured else tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def _action(client, action: str, state: str) -> None:
    await client.request("input.action", {"action": action, "state": state})


async def _joy_button(client, button: str, device: int = 0) -> None:
    await client.request(
        "input.joypad_button", {"button": button, "state": "press", "device": device}
    )
    await asyncio.sleep(0.03)
    await client.request(
        "input.joypad_button", {"button": button, "state": "release", "device": device}
    )
    await asyncio.sleep(0.08)


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_keyboard_steering_is_progressive_and_camera_independent(tmp_path: Path) -> None:
    artifacts = _artifacts(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input", "screenshot"),
        # Windows hosted runners using the ANGLE software renderer can take
        # more than ten seconds to service the first post-socket request. Keep
        # the timeout bounded while probing the responsive gameplay scene.
        request_timeout=30.0,
        transcript=artifacts / "driving-input-keyboard.jsonl",
        log_path=artifacts / "driving-input-keyboard-godot.log",
    )
    async with process as client:
        ready = await client.describe("vehicle.input.conditioner")
        assert ready["test_state"]["active_profile"] == "balanced"

        await _action(client, "steer_right", "press")
        try:
            deadline = asyncio.get_running_loop().time() + 1.0
            while True:
                early = (await client.describe("vehicle.input.conditioner"))["test_state"]
                if early["device_source"] == "keyboard" and early["raw_steering"] == 1:
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    pytest.fail("Keyboard steering event did not reach the input conditioner")
                await asyncio.sleep(0.02)
            assert early["device_source"] == "keyboard"
            assert early["active_profile"] == "balanced"
            assert early["keyboard_rise_per_second"] == pytest.approx(3.2)
            assert early["raw_steering"] == 1
            assert 0 < early["conditioned_steering"] <= 1

            await asyncio.sleep(0.15)
            later = (await client.describe("vehicle.input.conditioner"))["test_state"]
            assert early["conditioned_steering"] <= later["conditioned_steering"] <= 1
            camera = (await client.describe("camera.chase.rig"))["test_state"]
            assert camera["inherits_vehicle_rotation"] is False
            assert camera["horizon_roll_degrees"] < 0.01
            screenshot = await client.screenshot(artifacts / "input-steering.png")
            assert screenshot["bytes"] > 0
            assert screenshot["width"] >= 960
            assert screenshot["height"] >= 540
        finally:
            await _action(client, "steer_right", "release")

        await asyncio.sleep(0.05)
        returning = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert 0 <= returning["conditioned_steering"] < later["conditioned_steering"]

        await _action(client, "steer_left", "press")
        try:
            await asyncio.sleep(0.05)
            changing = (await client.describe("vehicle.input.conditioner"))["test_state"]
            assert changing["conditioned_steering"] > -0.5
            assert changing["steering_target"] == -1
        finally:
            await _action(client, "steer_left", "release")

        await _action(client, "reverse", "press")
        try:
            await asyncio.sleep(0.05)
            reverse = (await client.describe("vehicle.input.conditioner"))["test_state"]
            assert reverse["raw_reverse"] == 1
            assert reverse["conditioned_reverse"] > 0
            assert reverse["conditioned_throttle"] == 0
        finally:
            await _action(client, "reverse", "release")

        await _action(client, "handbrake", "press")
        try:
            await asyncio.sleep(0.05)
            handbrake = (await client.describe("vehicle.input.conditioner"))["test_state"]
            assert handbrake["raw_handbrake"] == 1
            assert handbrake["conditioned_handbrake"] > 0
            assert handbrake["conditioned_reverse"] == 0
        finally:
            await _action(client, "handbrake", "release")

        await _action(client, "cycle_assist", "press")
        await asyncio.sleep(0.03)
        await _action(client, "cycle_assist", "release")
        await asyncio.sleep(0.05)
        profile = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert profile["active_profile"] == "raw"


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_controller_deadzone_curve_and_independent_axes(tmp_path: Path) -> None:
    artifacts = _artifacts(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input"),
        transcript=artifacts / "driving-input-controller.jsonl",
        log_path=artifacts / "driving-input-controller-godot.log",
    )
    async with process as client:
        await client.request(
            "input.joypad_motion", {"axis": "left_y", "value": -1, "device": 3}
        )
        await asyncio.sleep(0.05)
        forward_stick = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert forward_stick["device_source"] == "keyboard"
        assert forward_stick["raw_throttle"] == 0
        assert forward_stick["raw_service_brake"] == 0
        assert forward_stick["conditioned_throttle"] == 0
        assert forward_stick["conditioned_steering"] == 0
        await client.request(
            "input.joypad_motion", {"axis": "left_y", "value": 0, "device": 3}
        )

        motion = await client.request(
            "input.joypad_motion", {"axis": "left_x", "value": 0.08, "device": 3}
        )
        assert motion["device"] == 3
        await asyncio.sleep(0.05)
        deadzone = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert deadzone["device_source"] == "keyboard"
        assert deadzone["controller_deadzone"] == pytest.approx(0.12)
        assert deadzone["controller_exponent"] == pytest.approx(1.35)
        assert deadzone["controller_rate_per_second"] == pytest.approx(4.5)
        assert deadzone["conditioned_steering"] == 0

        await _action(client, "accelerate", "press")
        try:
            await asyncio.sleep(0.05)
            keyboard = (await client.describe("vehicle.input.conditioner"))["test_state"]
            assert keyboard["device_source"] == "keyboard"
            assert keyboard["conditioned_throttle"] > 0
            assert keyboard["conditioned_steering"] == 0
        finally:
            await _action(client, "accelerate", "release")

        await client.request(
            "input.joypad_motion", {"axis": "left_x", "value": 0.5, "device": 3}
        )
        await asyncio.sleep(0.03)
        tagged = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert tagged["active_controller_device"] == 3
        await client.request(
            "input.joypad_motion", {"axis": "left_x", "value": 0, "device": 3}
        )

        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": -1, "device": 3}
        )
        await asyncio.sleep(0.05)
        wrong_polarity = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert wrong_polarity["conditioned_throttle"] == 0
        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 0.08, "device": 3}
        )
        await asyncio.sleep(0.05)
        trigger_deadzone = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert trigger_deadzone["conditioned_throttle"] == 0
        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 0, "device": 3}
        )

        await client.request("input.joypad_motion", {"axis": "left_x", "value": 0.5})
        await asyncio.sleep(0.08)
        curved = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert curved["device_source"] == "controller"
        assert curved["active_controller_device"] == 0
        assert 0 < curved["conditioned_steering"] < 0.5
        assert 0 < curved["steering_target"] < 0.5

        await client.request("input.joypad_motion", {"axis": "trigger_right", "value": 1})
        await asyncio.sleep(0.08)
        throttle = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert throttle["raw_throttle"] > 0.99
        assert throttle["conditioned_throttle"] > 0
        assert throttle["raw_service_brake"] == 0
        assert throttle["stationary_hold"] is False

        await client.request("input.joypad_motion", {"axis": "trigger_left", "value": 1})
        await asyncio.sleep(0.08)
        braking = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert braking["raw_service_brake"] > 0.99
        assert braking["conditioned_service_brake"] > 0
        assert braking["conditioned_throttle"] == 0

        button = await client.request(
            "input.joypad_button", {"button": "x", "state": "press", "device": 3}
        )
        assert button["device"] == 3
        await client.request(
            "input.joypad_button", {"button": "x", "state": "release", "device": 3}
        )
        await client.request("input.joypad_button", {"button": "x", "state": "press"})
        await asyncio.sleep(0.05)
        handbrake = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert handbrake["raw_handbrake"] == 1
        await client.request("input.joypad_button", {"button": "x", "state": "release"})

        await client.request("input.joypad_motion", {"axis": "left_x", "value": 0})
        await client.request("input.joypad_motion", {"axis": "trigger_right", "value": 0})
        await client.request("input.joypad_motion", {"axis": "trigger_left", "value": 0})


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_controller_focus_loss_disconnect_and_reconnect_clear_state(
    tmp_path: Path,
) -> None:
    artifacts = _artifacts(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input"),
        transcript=artifacts / "driving-input-controller-lifecycle.jsonl",
        log_path=artifacts / "driving-input-controller-lifecycle-godot.log",
    )
    async with process as client:
        await client.request("input.joy_connection", {"device": 3, "connected": True})
        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 1, "device": 3}
        )
        await asyncio.sleep(0.08)
        active = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert active["active_controller_device"] == 3
        assert active["conditioned_throttle"] > 0

        await client.request("input.application_focus", {"state": "out"})
        await asyncio.sleep(0.05)
        unfocused = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert unfocused["conditioned_throttle"] == 0
        assert unfocused["input_suppressed"] is True
        assert unfocused["suppression_reason"] == "focus_loss"

        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 0, "device": 3}
        )
        await client.request("input.application_focus", {"state": "in"})
        await asyncio.sleep(0.08)
        refocused = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert refocused["conditioned_throttle"] == 0
        assert refocused["input_suppressed"] is False

        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 1, "device": 3}
        )
        await asyncio.sleep(0.08)
        await client.request("input.joy_connection", {"device": 3, "connected": False})
        await asyncio.sleep(0.05)
        disconnected = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert disconnected["active_controller_device"] == -1
        assert disconnected["conditioned_throttle"] == 0

        await client.request("input.joy_connection", {"device": 3, "connected": True})
        await client.request(
            "input.joypad_motion", {"axis": "left_x", "value": 0.5, "device": 3}
        )
        await asyncio.sleep(0.08)
        reconnected = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert reconnected["active_controller_device"] == 3
        assert reconnected["input_suppressed"] is False
        assert reconnected["conditioned_throttle"] == 0
        assert reconnected["conditioned_steering"] > 0
        await client.request(
            "input.joypad_motion", {"axis": "left_x", "value": 0, "device": 3}
        )


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_controller_camera_recover_menu_and_confirmed_restart_are_distinct(
    tmp_path: Path,
) -> None:
    artifacts = _artifacts(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input"),
        request_timeout=30.0,
        transcript=artifacts / "driving-input-controller-restart.jsonl",
        log_path=artifacts / "driving-input-controller-restart-godot.log",
    )
    async with process as client:
        await _joy_button(client, "right_stick", device=2)
        assert (await client.describe("camera.cockpit.view"))["test_state"]["active"] is True
        await client.request(
            "input.joypad_button", {"button": "left_shoulder", "state": "press", "device": 2}
        )
        await asyncio.sleep(0.25)
        physical_rear = (await client.describe("camera.cockpit.view"))["test_state"]
        assert physical_rear["rear_view_held"] is True
        assert abs(physical_rear["displayed_yaw_degrees"]) > 170
        await client.request(
            "input.joypad_button", {"button": "left_shoulder", "state": "release", "device": 2}
        )
        await asyncio.sleep(0.25)

        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 1, "device": 2}
        )
        await asyncio.sleep(1.0)
        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 0, "device": 2}
        )
        await asyncio.sleep(0.15)
        progressed = (await client.describe("run.session"))["test_state"]
        assert progressed["route_distance_m"] > 0.5
        assert progressed["restart_count"] == 0

        await _joy_button(client, "y", device=2)
        recovered = (await client.describe("run.session"))["test_state"]
        assert recovered["restart_count"] == 0
        assert recovered["route_distance_m"] > 0.5
        assert recovered["camera_mode"] == "cockpit"

        await _joy_button(client, "start", device=2)
        menu = (await client.describe("menu.driver.root"))["test_state"]
        assert menu["open"] is True
        assert menu["button_count"] == 4
        assert menu["restart_confirmation_armed"] is False
        assert (await client.request("ui.focused"))["automation_id"] == "menu.driver.resume"

        for _ in range(3):
            await _joy_button(client, "dpad_down", device=2)
        assert (await client.request("ui.focused"))["automation_id"] == "menu.driver.restart-run"

        await _joy_button(client, "a", device=2)
        armed = (await client.describe("menu.driver.root"))["test_state"]
        assert armed["open"] is True
        assert armed["restart_confirmation_armed"] is True
        await _joy_button(client, "a", device=2)

        deadline = asyncio.get_running_loop().time() + 2.0
        while True:
            restarted = (await client.describe("run.session"))["test_state"]
            if restarted["restart_count"] == 1:
                break
            if asyncio.get_running_loop().time() >= deadline:
                pytest.fail("Confirmed controller restart did not rebuild the run")
            await asyncio.sleep(0.02)

        assert restarted["route_distance_m"] == pytest.approx(0, abs=0.001)
        assert restarted["edge_distance_m"] == pytest.approx(0, abs=0.001)
        assert restarted["start_horizontal_error_m"] < 0.01
        assert restarted["start_rotation_dot"] == pytest.approx(1, abs=0.0001)
        assert restarted["last_restart_route_distance_m"] == 0
        assert restarted["last_restart_position_error_m"] == 0
        assert restarted["last_restart_rotation_dot"] == pytest.approx(1, abs=0.0001)
        assert restarted["last_restart_linear_speed_mps"] == 0
        assert restarted["last_restart_angular_speed_radps"] == 0
        assert restarted["elapsed_seconds"] < 1
        assert restarted["camera_mode"] == "chase"
        assert restarted["seed"] == progressed["seed"]
        assert restarted["cash"] == 25_000


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_pause_clears_held_input_until_neutral(tmp_path: Path) -> None:
    artifacts = _artifacts(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input"),
        transcript=artifacts / "driving-input-pause.jsonl",
        log_path=artifacts / "driving-input-pause-godot.log",
    )
    async with process as client:
        await _action(client, "accelerate", "press")
        await asyncio.sleep(0.08)
        assert (
            await client.describe("vehicle.input.conditioner")
        )["test_state"]["conditioned_throttle"] > 0

        await client.request("input.key", {"key": "Escape", "state": "press"})
        await client.request("input.key", {"key": "Escape", "state": "release"})
        await asyncio.sleep(0.05)
        paused = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert paused["conditioned_throttle"] == 0
        assert paused["input_suppressed"] is True
        assert paused["suppression_reason"] == "pause"

        await _action(client, "accelerate", "release")
        await client.request("input.click", {"automation_id": "menu.driver.resume"})
        await asyncio.sleep(0.08)
        resumed = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert resumed["conditioned_throttle"] == 0
        assert resumed["input_suppressed"] is False
        assert resumed["suppression_reason"] == "none"


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_stationary_hold_prevents_uncommanded_route_start_rollback(tmp_path: Path) -> None:
    artifacts = _artifacts(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read",),
        transcript=artifacts / "driving-input-hold.jsonl",
        log_path=artifacts / "driving-input-hold-godot.log",
    )
    async with process as client:
        await asyncio.sleep(0.8)
        input_state = (await client.describe("vehicle.input.conditioner"))["test_state"]
        camera_state = (await client.describe("camera.chase.rig"))["test_state"]
        assert input_state["stationary_hold"] is True
        assert input_state["conditioned_throttle"] == 0
        assert input_state["conditioned_reverse"] == 0
        assert abs(input_state["forward_speed_mps"]) < 0.05
        assert camera_state["speed_mps"] < 1
