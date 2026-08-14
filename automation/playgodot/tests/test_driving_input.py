from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from cannonball_playgodot import PlayGodotProcess

from .input_support import wait_for_conditioner, wait_for_key_conditioner

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

        try:
            early = await wait_for_key_conditioner(
                client,
                key="D",
                raw_field="raw_steering",
                predicate=lambda state: state["device_source"] == "keyboard",
                failure="Keyboard steering event did not reach the input conditioner",
            )
            assert early["device_source"] == "keyboard"
            assert early["active_profile"] == "balanced"
            assert early["keyboard_rise_per_second"] == pytest.approx(3.2)
            assert early["raw_steering"] == 1
            assert 0 < early["conditioned_steering"] <= 1

            later = await wait_for_key_conditioner(
                client,
                key="D",
                raw_field="raw_steering",
                predicate=lambda state: (
                    state["conditioned_steering"] > early["conditioned_steering"]
                ),
                failure=(
                    "Keyboard steering did not exhibit progressive conditioning; "
                    f"early={early}"
                ),
            )
            assert early["conditioned_steering"] < later["conditioned_steering"] <= 1
            release_steering = later["conditioned_steering"]
            camera = (await client.describe("camera.chase.rig"))["test_state"]
            assert camera["inherits_vehicle_rotation"] is False
            assert camera["horizon_roll_degrees"] < 0.01
            screenshot = await client.screenshot(artifacts / "input-steering.png")
            assert screenshot["bytes"] > 0
            assert screenshot["width"] >= 960
            assert screenshot["height"] >= 540
            assert 0 < release_steering <= 1
        finally:
            await client.request("input.key", {"key": "D", "state": "release"})

        deadline = asyncio.get_running_loop().time() + 1.0
        while True:
            returning = (await client.describe("vehicle.input.conditioner"))["test_state"]
            if asyncio.get_running_loop().time() >= deadline:
                pytest.fail(
                    "Keyboard steering did not decay after release; "
                    f"release value was {release_steering} and current value is "
                    f"{returning['conditioned_steering']}"
                )
            if 0 <= returning["conditioned_steering"] < release_steering:
                break
            await asyncio.sleep(0.02)

        assert 0 <= returning["conditioned_steering"] < release_steering

        await _action(client, "steer_left", "press")
        try:
            # Observe the ramp while it is still between centre and full left.
            #
            # This previously slept a fixed 50 ms and asserted the value had not
            # passed -0.5, which encodes an assumption about how far the ramp
            # travels in that window. A loaded Windows runner services the
            # request later, so more physics steps elapse and the ramp goes
            # further: the gate failed at -0.587 against the -0.5 bound while the
            # build was correct. The contract P0-018 states is that steering
            # ramps in rather than snapping to full lock, so wait for the first
            # sample that has moved off centre and assert it is short of the
            # lock, which holds at any runner speed.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 1.0
            changing: dict[str, object] | None = None
            while True:
                # The one second bound has to hold even if a single describe
                # stalls: the client's own request timeout is 30 s, so without
                # bounding the await this loop could run far past its deadline.
                remaining = deadline - loop.time()
                if remaining <= 0:
                    pytest.fail(
                        "Keyboard steering did not condition toward full left "
                        f"within 1 s; last conditioner state was {changing}"
                    )
                changing = (
                    await asyncio.wait_for(
                        client.describe("vehicle.input.conditioner"),
                        timeout=remaining,
                    )
                )["test_state"]
                # Check the deadline before accepting the sample, so a reading
                # that arrives late cannot satisfy the wait.
                if loop.time() >= deadline:
                    pytest.fail(
                        "Keyboard steering conditioned toward full left only "
                        f"after the 1 s bound; conditioner state was {changing}"
                    )
                if changing["conditioned_steering"] < 0:
                    break
                await asyncio.sleep(0.02)

            assert -1 < changing["conditioned_steering"] < 0
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
        throttle = None
        for _ in range(80):
            await asyncio.sleep(0.025)
            sample = (await client.describe("vehicle.input.conditioner"))["test_state"]
            if sample["forward_speed_mps"] > 4:
                throttle = sample
                break
        assert throttle is not None
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
        assert braking["brake_trigger_reverse_engaged"] is False
        assert braking["brake_to_reverse_enter_speed_mps"] == pytest.approx(0.35)
        assert braking["brake_to_reverse_exit_speed_mps"] == pytest.approx(0.75)

        await client.request("input.joypad_motion", {"axis": "trigger_right", "value": 0})
        reverse_handoff = None
        for _ in range(80):
            await asyncio.sleep(0.025)
            sample = (await client.describe("vehicle.input.conditioner"))["test_state"]
            if (
                sample["brake_trigger_reverse_engaged"]
                and sample["conditioned_reverse"] > 0
                and sample["forward_speed_mps"] < -0.05
                and sample["conditioned_service_brake"]
                < braking["conditioned_service_brake"]
            ):
                reverse_handoff = sample
                break
        assert reverse_handoff is not None
        assert reverse_handoff["raw_service_brake"] > 0.99
        assert reverse_handoff["raw_reverse"] == 0
        assert 0 <= reverse_handoff["conditioned_service_brake"] < braking[
            "conditioned_service_brake"
        ]
        assert reverse_handoff["conditioned_throttle"] == 0

        await asyncio.sleep(0.1)
        settled_reverse = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert settled_reverse["brake_trigger_reverse_engaged"] is True
        assert settled_reverse["conditioned_service_brake"] == 0
        assert settled_reverse["conditioned_reverse"] >= reverse_handoff["conditioned_reverse"]

        await client.request("input.joypad_motion", {"axis": "trigger_left", "value": 0})
        await client.request("input.joypad_button", {"button": "b", "state": "press"})
        await asyncio.sleep(0.08)
        secondary_reverse = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert secondary_reverse["raw_reverse"] == 1
        assert secondary_reverse["conditioned_reverse"] > 0
        assert secondary_reverse["brake_trigger_reverse_engaged"] is False
        await client.request("input.joypad_button", {"button": "b", "state": "release"})

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
        await wait_for_conditioner(
            client,
            lambda state: (
                state["active_controller_device"] == 3
                and state["conditioned_throttle"] > 0
            ),
            "Controller throttle did not become active",
        )
        before_focus_loss = (
            await client.describe("vehicle.input.conditioner")
        )["test_state"]["suppression_sequence"]
        await client.request("input.application_focus", {"state": "out"})
        await wait_for_conditioner(
            client,
            lambda state: (
                state["conditioned_throttle"] == 0
                and state["suppression_sequence"] > before_focus_loss
                and state["last_suppression_reason"] == "focus_loss"
            ),
            "Focus loss did not suppress controller input",
        )
        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 0, "device": 3}
        )
        await client.request("input.application_focus", {"state": "in"})
        await wait_for_conditioner(
            client,
            lambda state: state["conditioned_throttle"] == 0
            and state["input_suppressed"] is False,
            "Neutral controller input did not recover after focus returned",
        )
        await client.request(
            "input.joypad_motion", {"axis": "trigger_right", "value": 1, "device": 3}
        )
        await wait_for_conditioner(
            client,
            lambda state: state["conditioned_throttle"] > 0,
            "Controller throttle did not reactivate before disconnect",
        )
        await client.request("input.joy_connection", {"device": 3, "connected": False})
        await wait_for_conditioner(
            client,
            lambda state: (
                state["active_controller_device"] == -1
                and state["conditioned_throttle"] == 0
            ),
            "Controller disconnect did not clear active input",
        )
        await client.request("input.joy_connection", {"device": 3, "connected": True})
        await client.request(
            "input.joypad_motion", {"axis": "left_x", "value": 0.5, "device": 3}
        )
        await wait_for_conditioner(
            client,
            lambda state: (
                state["active_controller_device"] == 3
                and state["input_suppressed"] is False
                and state["conditioned_throttle"] == 0
                and state["conditioned_steering"] > 0
            ),
            "Reconnected controller did not regain neutral steering authority",
        )
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
        rear_deadline = asyncio.get_running_loop().time() + 3.0
        physical_rear: dict = {}
        while True:
            remaining = rear_deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                pytest.fail(f"Physical rear view did not settle; last state={physical_rear}")
            try:
                physical_rear = (
                    await asyncio.wait_for(
                        client.describe("camera.cockpit.view"), timeout=remaining
                    )
                )["test_state"]
            except TimeoutError:
                pytest.fail(f"Physical rear-view query timed out; last state={physical_rear}")
            if physical_rear["rear_view_held"] and abs(
                physical_rear["displayed_yaw_degrees"]
            ) > 170:
                break
            remaining = rear_deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                pytest.fail(f"Physical rear view did not settle; last state={physical_rear}")
            try:
                await asyncio.wait_for(asyncio.sleep(0.05), timeout=remaining)
            except TimeoutError:
                pytest.fail(f"Physical rear view did not settle; last state={physical_rear}")
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

        neutral_deadline = asyncio.get_running_loop().time() + 1.0
        while True:
            input_state = (await client.describe("vehicle.input.conditioner"))["test_state"]
            if input_state["input_suppressed"] is False:
                break
            if asyncio.get_running_loop().time() >= neutral_deadline:
                pytest.fail("Recover input suppression did not clear after controller neutral")
            await asyncio.sleep(0.02)

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
        await wait_for_key_conditioner(
            client,
            key="W",
            raw_field="raw_throttle",
            predicate=lambda state: state["conditioned_throttle"] > 0,
            failure="Throttle did not become active before pause",
        )
        before_pause = (
            await client.describe("vehicle.input.conditioner")
        )["test_state"]["suppression_sequence"]

        wait_for_pause = asyncio.create_task(
            client.request(
                "signal.wait",
                {
                    "automation_id": "menu.driver.root",
                    "signal": "visibility_changed",
                    "timeout_ms": 2_000,
                },
            )
        )
        await asyncio.sleep(0)
        await client.request("input.key", {"key": "Escape", "state": "press"})
        await client.request("input.key", {"key": "Escape", "state": "release"})
        assert (await wait_for_pause)["signal"] == "visibility_changed"

        menu = await client.describe("menu.driver.root")
        assert menu["visible"] is True
        assert menu["test_state"]["simulation_paused"] is True
        paused = await wait_for_conditioner(
            client,
            lambda state: (
                state["suppression_sequence"] > before_pause
                and state["last_suppression_reason"] == "pause"
                and state["conditioned_throttle"] == 0
            ),
            "Pause did not suppress held input",
        )
        assert paused["conditioned_throttle"] == 0
        assert paused["stationary_hold"] is True
        assert paused["suppression_sequence"] > before_pause
        assert paused["last_suppression_reason"] == "pause"

        await client.request("input.key", {"key": "W", "state": "release"})
        wait_for_resume = asyncio.create_task(
            client.request(
                "signal.wait",
                {
                    "automation_id": "menu.driver.root",
                    "signal": "visibility_changed",
                    "timeout_ms": 2_000,
                },
            )
        )
        await asyncio.sleep(0)
        await client.request("input.click", {"automation_id": "menu.driver.resume"})
        assert (await wait_for_resume)["signal"] == "visibility_changed"

        menu = await client.describe("menu.driver.root")
        assert menu["visible"] is False
        assert menu["test_state"]["simulation_paused"] is False
        deadline = asyncio.get_running_loop().time() + 2.0
        while True:
            resumed = (await client.describe("vehicle.input.conditioner"))["test_state"]
            if resumed["input_suppressed"] is False:
                break
            if asyncio.get_running_loop().time() >= deadline:
                pytest.fail(f"Input suppression did not clear after resume; state={resumed}")
            await asyncio.sleep(0.02)
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
