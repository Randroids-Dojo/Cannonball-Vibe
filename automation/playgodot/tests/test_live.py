from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from PIL import Image

from cannonball_playgodot import (
    PlayGodotClient,
    PlayGodotError,
    PlayGodotProcess,
    ProtocolError,
)

from .input_support import wait_for_describe, wait_for_key_conditioner

REPO_ROOT = Path(__file__).resolve().parents[3]


def _route_package() -> Path:
    package_root = REPO_ROOT / ".tools/scenarios/official-corridor"
    pointer = json.loads((package_root / "current-package.json").read_text())
    return package_root / pointer["root_relative_path"]


def _artifact_directory(tmp_path: Path) -> Path:
    configured = os.environ.get("PLAYGODOT_ARTIFACT_DIR")
    directory = Path(configured) if configured else tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextlib.asynccontextmanager
async def _raw_server(tmp_path: Path) -> AsyncIterator[tuple[str, int, str, Path]]:
    transcript = tmp_path / "hostile.jsonl"
    process = PlayGodotProcess(
        REPO_ROOT, _route_package(), capabilities=("read", "input", "screenshot"),
        transcript=transcript, log_path=tmp_path / "raw-godot.log",
    )
    original: BaseException | None = None
    try:
        client = await process.start()
        # Raw probes retain their own wire-level handshakes. Close only this
        # connection; the same process owner remains responsible for quit/exit.
        await client.close()
        process.client = None
        assert process._shutdown_endpoint is not None and process._shutdown_token is not None
        yield (*process._shutdown_endpoint, process._shutdown_token, transcript)
    except BaseException as error:
        original = error
        raise
    finally:
        await process._stop_preserving(original)


async def _raw_request(
    host: str, port: int, payload: bytes, *, allow_empty: bool = False
) -> dict | None:
    """Send one raw line and return the decoded response.

    The bridge accepts a single connection at a time and refuses a new
    candidate while a stale previous peer has not yet been observed as closed,
    dropping it without any response. A connection reset or an empty read is
    therefore a transient of connection turnover, never an answer: retry it
    within a bounded deadline (red-main #100 was this returning None on
    Windows CI and the caller subscripting it). Refused candidates carry no
    application data, so retrying cannot double-apply a request.

    ``allow_empty`` callers accept "closed without a response" as a legitimate
    final outcome (the oversized-request probe); everyone else gets a failure
    with diagnostics when the deadline expires.
    """
    deadline = asyncio.get_running_loop().time() + 5.0
    while True:
        empty_reason = "connection closed before a response line arrived"
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except ConnectionError:
            empty_reason = "connection attempt was refused"
        else:
            try:
                writer.write(payload + b"\n")
                await writer.drain()
                line = await asyncio.wait_for(reader.readline(), 2)
                if line:
                    return json.loads(line)
            except ConnectionResetError:
                empty_reason = "connection was reset before a response line arrived"
            finally:
                writer.close()
                with contextlib.suppress(ConnectionError):
                    await writer.wait_closed()
        if asyncio.get_running_loop().time() >= deadline:
            if allow_empty:
                return None
            pytest.fail(f"Raw request retry deadline expired; last attempt: {empty_reason}")
        await asyncio.sleep(0.05)


async def _connect_after_session_cleanup(
    host: str,
    port: int,
    *,
    token: str,
    capabilities: tuple[str, ...] = ("read",),
) -> PlayGodotClient:
    deadline = asyncio.get_running_loop().time() + 2
    while True:
        try:
            return await PlayGodotClient.connect(
                host,
                port,
                token=token,
                capabilities=capabilities,
                timeout=1,
            )
        except (OSError, ProtocolError):
            if asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(0.05)


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_official_engine_semantic_round_trip(tmp_path: Path) -> None:
    artifacts = _artifact_directory(tmp_path)
    transcript = artifacts / "round-trip.jsonl"
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input", "screenshot"),
        transcript=transcript,
        log_path=artifacts / "godot.log",
    )
    async with process as client:
        startup = list(process.output)
        first_frame = next(
            index for index, line in enumerate(startup)
            if line.startswith("PLAYGODOT_FIRST_FRAME ")
        )
        ready = next(
            index for index, line in enumerate(startup)
            if line.startswith("PLAYGODOT_READY ")
        )
        assert first_frame < ready
        assert any(line.startswith("CANNONBALL_READY ") for line in startup[:first_frame])
        capabilities = await client.request("session.capabilities")
        assert capabilities["granted"] == ["read", "input", "screenshot"]
        assert capabilities["limits"]["tree_nodes"] == 512

        streamer = await client.describe("world.streamer")
        assert streamer["test_state"]["initial_route_distance_m"] == 0
        assert streamer["test_state"]["initial_vehicle_lane_id"]
        assert streamer["test_state"]["route_start_apron_m"] == 20
        assert streamer["test_state"]["route_start_barrier"] is True
        assert streamer["test_state"]["route_start_barrier_collision"] is True

        chase_camera = await client.describe("camera.chase.rig")
        camera_state = chase_camera["test_state"]
        assert camera_state["mode"] == "chase"
        assert camera_state["top_level"] is True
        assert camera_state["inherits_vehicle_rotation"] is False
        assert camera_state["collision_mask"] == 1
        assert camera_state["horizon_roll_degrees"] < 0.01
        assert camera_state["spring_length_m"] >= 7.5
        assert camera_state["active"] is True

        cockpit_camera = await client.describe("camera.cockpit.view")
        cockpit_state = cockpit_camera["test_state"]
        assert cockpit_state["active"] is False
        assert cockpit_state["mode"] == "cockpit"
        assert cockpit_state["vehicle_local"] is True
        assert cockpit_state["maximum_stabilization_degrees"] == 6
        assert cockpit_state["maximum_look_yaw_degrees"] == 72
        assert cockpit_state["maximum_look_pitch_degrees"] == 24
        # The camera toggle is polled by the vehicle, so hold the action until
        # its effect is observed before releasing: releasing after a fixed
        # sleep raced the polling tick and could drop the toggle entirely.
        await client.request("input.action", {"action": "toggle_camera", "state": "press"})
        await wait_for_describe(
            client,
            "camera.cockpit.view",
            lambda state: state["test_state"]["active"] is True,
            "Camera toggle to cockpit was not observed",
        )
        await client.request("input.action", {"action": "toggle_camera", "state": "release"})
        assert (await client.describe("camera.chase.rig"))["test_state"]["active"] is False
        assert (await client.describe("camera.cockpit.view"))["test_state"]["active"] is True
        # The camera toggle is edge-detected in the vehicle's physics phase, so
        # the release must be observed by a physics tick before the next press
        # can register a rising edge. 50 ms accumulates several 120 Hz ticks on
        # any runner; without it the re-press can land in a frame whose physics
        # phase never saw the released state, and the second toggle is lost.
        await asyncio.sleep(0.05)
        await client.request("input.action", {"action": "toggle_camera", "state": "press"})
        await wait_for_describe(
            client,
            "camera.chase.rig",
            lambda state: state["test_state"]["active"] is True,
            "Camera toggle back to chase was not observed",
        )
        await client.request("input.action", {"action": "toggle_camera", "state": "release"})
        assert (await client.describe("camera.chase.rig"))["test_state"]["active"] is True

        speed = await client.describe("hud.speed")
        assert speed["automation_id"] == "hud.speed"
        assert speed["class"] == "Label"
        assert speed["visible"] is True
        assert speed["text"].endswith(" MPH")
        assert speed["bounds"]["width"] > 40
        assert speed["bounds"]["height"] > 20

        driver_menu = await client.describe("menu.driver.root")
        assert driver_menu["visible"] is False
        wait_for_menu = asyncio.create_task(
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
        assert (await wait_for_menu)["signal"] == "visibility_changed"

        driver_menu = await client.describe("menu.driver.root")
        assert driver_menu["visible"] is True
        assert driver_menu["test_state"] == {
            "button_count": 4,
            "open": True,
            "restart_confirmation_armed": False,
            "simulation_paused": True,
            "status": "Paused at current route position",
        }
        focused = await client.request("ui.focused")
        assert focused["automation_id"] == "menu.driver.resume"
        assert focused["text"] == "RESUME DRIVE"

        await client.request("input.click", {"automation_id": "menu.driver.options"})
        menu_status = await client.describe("menu.driver.status")
        assert menu_status["text"] == "Driving options selected"
        driver_menu = await client.describe("menu.driver.root")
        assert driver_menu["test_state"]["status"] == "Driving options selected"

        menu_path = artifacts / "driver-menu.png"
        menu_screenshot = await client.screenshot(
            menu_path, automation_id="menu.driver.root"
        )
        assert menu_screenshot["bytes"] > 0
        assert menu_screenshot["width"] >= 300
        assert menu_screenshot["height"] >= 350

        wait_for_close = asyncio.create_task(
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
        assert (await wait_for_close)["signal"] == "visibility_changed"
        closed_menu = await client.describe("menu.driver.root")
        assert closed_menu["visible"] is False
        assert closed_menu["test_state"] == {
            "button_count": 4,
            "open": False,
            "restart_confirmation_armed": False,
            "simulation_paused": False,
            "status": "closed",
        }

        trip_map = await client.describe("trip-map.root")
        assert trip_map["visible"] is False
        wait_for_trip_map = asyncio.create_task(
            client.request(
                "signal.wait",
                {
                    "automation_id": "trip-map.root",
                    "signal": "visibility_changed",
                    "timeout_ms": 2_000,
                },
            )
        )
        await asyncio.sleep(0)
        # The trip-map toggle is polled by Main, so hold the action until the
        # visibility change confirms it was observed before releasing.
        await client.request(
            "input.action", {"action": "toggle_trip_map", "state": "press"}
        )
        assert (await wait_for_trip_map)["signal"] == "visibility_changed"
        await client.request(
            "input.action", {"action": "toggle_trip_map", "state": "release"}
        )

        trip_map = await client.describe("trip-map.root")
        assert trip_map["visible"] is True
        assert trip_map["test_state"]["open"] is True
        assert trip_map["test_state"]["simulation_paused"] is True
        assert trip_map["test_state"]["distance_remaining_m"] > 0
        assert trip_map["test_state"]["feature_count"] >= 0
        assert trip_map["test_state"]["geometry_lod"] == 0
        assert trip_map["test_state"]["projected_point_count"] > 0
        assert trip_map["test_state"]["travel_mode_id"] == "real-time"
        assert trip_map["test_state"]["travel_time_scale"] == 1
        assert 0 <= trip_map["test_state"]["progress_percent"] <= 100
        assert trip_map["test_state"]["legend_item_count"] == 6
        assert 0 < trip_map["test_state"]["draw_batch_count"] <= (
            trip_map["test_state"]["alternative_count"] + 2
        )
        summary = await client.describe("trip-map.summary")
        assert "mi completed" in summary["text"]
        assert "mi remaining" in summary["text"]
        assert "1:1 endurance" in summary["text"]
        progress = await client.describe("trip-map.progress")
        assert progress["visible"] is True
        assert (
            summary["bounds"]["y"] + summary["bounds"]["height"]
            <= progress["bounds"]["y"]
        )
        legend = await client.describe("trip-map.legend")
        assert legend["visible"] is True
        selection = await client.describe("trip-map.selection")
        assert (
            summary["bounds"]["y"] + summary["bounds"]["height"]
            <= selection["bounds"]["y"]
        )

        initial_zoom = trip_map["test_state"]["zoom"]
        await client.request("input.click", {"automation_id": "trip-map.zoom-in"})
        zoomed_map = await client.describe("trip-map.root")
        assert zoomed_map["test_state"]["zoom"] > initial_zoom
        await client.request("input.click", {"automation_id": "trip-map.recenter"})
        recentered_map = await client.describe("trip-map.root")
        assert recentered_map["test_state"]["zoom"] == 1
        assert recentered_map["test_state"]["pan_x"] == 0
        assert recentered_map["test_state"]["pan_y"] == 0

        trip_map_path = artifacts / "trip-map.png"
        trip_map_screenshot = await client.screenshot(
            trip_map_path, automation_id="trip-map.root"
        )
        assert trip_map_screenshot["bytes"] > 0
        assert trip_map_screenshot["width"] >= 960
        assert trip_map_screenshot["height"] >= 540
        assert trip_map_screenshot["width"] / trip_map_screenshot["height"] == pytest.approx(
            16 / 9, rel=0.02
        )

        await client.request("input.click", {"automation_id": "trip-map.close"})
        closed_trip_map = await client.describe("trip-map.root")
        assert closed_trip_map["visible"] is False
        assert closed_trip_map["test_state"]["simulation_paused"] is False

        with pytest.raises(PlayGodotError, match="DUPLICATE_ID"):
            await client.describe("playgodot.fixture.duplicate")

        tree = await client.tree(max_depth=1, max_nodes=4)
        assert tree["count"] <= 4
        assert tree["truncated"] is True

        wait = asyncio.create_task(
            client.request(
                "signal.wait",
                {
                    "automation_id": "playgodot.fixture.button",
                    "signal": "pressed",
                    "timeout_ms": 2_000,
                },
            )
        )
        await asyncio.sleep(0)
        click = await client.request("input.click", {"automation_id": "playgodot.fixture.button"})
        assert click["automation_id"] == "playgodot.fixture.button"
        assert (await wait)["signal"] == "pressed"

        with pytest.raises(PlayGodotError, match="TIMEOUT"):
            await client.request(
                "signal.wait",
                {
                    "automation_id": "playgodot.fixture.button",
                    "signal": "pressed",
                    "timeout_ms": 20,
                },
            )

        screenshot_path = artifacts / "speed.png"
        screenshot = await client.screenshot(screenshot_path, automation_id="hud.speed")
        assert screenshot["bytes"] > 0
        assert 0 < screenshot["width"] <= speed["bounds"]["width"]
        assert 0 < screenshot["height"] <= speed["bounds"]["height"]
        assert screenshot_path.read_bytes().startswith(b"\x89PNG")

        color_path = artifacts / "color.png"
        await client.screenshot(color_path, automation_id="playgodot.fixture.color")
        with Image.open(color_path) as color_image:
            center = color_image.convert("RGB").getpixel(
                (color_image.width // 2, color_image.height // 2)
            )
        assert center == pytest.approx((64, 128, 191), abs=1)

        viewport_path = artifacts / "viewport.png"
        viewport = await client.screenshot(viewport_path)
        assert viewport["width"] > screenshot["width"]
        assert viewport["height"] > screenshot["height"]

        with pytest.raises(PlayGodotError, match="METHOD_NOT_FOUND"):
            await client.request("node.set_property", {"name": "text", "value": "unsafe"})

    entries = [json.loads(line) for line in transcript.read_text().splitlines()]
    assert entries
    assert all("token" not in entry for entry in entries)
    assert all(
        set(entry) == {"request_id", "method", "outcome", "duration_ms"} for entry in entries
    )
    assert any(
        entry["method"] == "signal.wait" and entry["outcome"] == "timeout" for entry in entries
    )
    assert any(
        entry["method"] == "unknown" and entry["outcome"] == "method_not_found" for entry in entries
    )


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_trip_map_resume_preserves_vehicle_vertical_stability(tmp_path: Path) -> None:
    artifacts = _artifact_directory(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input"),
        transcript=artifacts / "trip-map-resume.jsonl",
        log_path=artifacts / "trip-map-resume-godot.log",
    )
    async with process as client:
        deadline = asyncio.get_running_loop().time() + 8.0
        while True:
            before = (await client.describe("run.session"))["test_state"]
            if before["grounded_wheel_count"] >= 3:
                break
            if asyncio.get_running_loop().time() >= deadline:
                pytest.fail(f"Vehicle did not settle before Trip Overview probe: {before}")
            await asyncio.sleep(0.02)

        last_input_state = await wait_for_key_conditioner(
            client,
            key="W",
            raw_field="raw_throttle",
            predicate=lambda current: current["conditioned_throttle"] > 0,
            failure="Vehicle input did not start the Trip Overview resume probe",
        )
        try:
            deadline = asyncio.get_running_loop().time() + 8.0
            while True:
                before = (await client.describe("run.session"))["test_state"]
                if before["linear_speed_mps"] >= 12 and before["grounded_wheel_count"] >= 3:
                    break

                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    pytest.fail(
                        "Vehicle did not reach the Trip Overview probe speed; "
                        f"session_state={before}, input_state={last_input_state}"
                    )
                last_input_state = await wait_for_key_conditioner(
                    client,
                    key="W",
                    raw_field="raw_throttle",
                    predicate=lambda current: current["conditioned_throttle"] > 0,
                    failure="Vehicle input did not stay active for the Trip Overview probe",
                    timeout=remaining,
                )
                await asyncio.sleep(0.02)

            # Hold the polled toggle action until the trip map is observed
            # open, then release: releasing after a fixed sleep raced the
            # polling frame and could drop the toggle entirely.
            await client.request(
                "input.action", {"action": "toggle_trip_map", "state": "press"}
            )
            trip_map = await wait_for_describe(
                client,
                "trip-map.root",
                lambda state: state["visible"] is True,
                "Trip Overview did not open for the resume probe",
            )
            await client.request(
                "input.action", {"action": "toggle_trip_map", "state": "release"}
            )
            assert trip_map["visible"] is True
            assert trip_map["test_state"]["simulation_paused"] is True
            paused_start = (await client.describe("run.session"))["test_state"]

            await asyncio.sleep(0.25)
            paused = (await client.describe("run.session"))["test_state"]
            for field in (
                "vehicle_position_x",
                "vehicle_position_y",
                "vehicle_position_z",
                "vehicle_linear_velocity_x",
                "vehicle_linear_velocity_y",
                "vehicle_linear_velocity_z",
            ):
                assert paused[field] == pytest.approx(paused_start[field], abs=0.001)

            await client.request("input.click", {"automation_id": "trip-map.close"})
            # Watch the resume transient until the vertical motion has settled:
            # the vehicle has demonstrably moved since the pause (so the
            # simulation is really running again) and two consecutive grounded
            # samples agree on vertical velocity. A fixed one-second wall-clock
            # window sampled a runner-dependent stretch of road, folding
            # legitimate terrain motion into the transient bounds; the settle
            # condition ends the watch deterministically, a resume impulse
            # defers settling until it has been captured, and the generous
            # deadline fails with diagnostics instead of racing.
            samples = []
            deadline = asyncio.get_running_loop().time() + 8.0
            previous = None
            while True:
                sample = (await client.describe("run.session"))["test_state"]
                samples.append(sample)
                moved_meters = max(
                    abs(sample["vehicle_position_x"] - paused["vehicle_position_x"]),
                    abs(sample["vehicle_position_z"] - paused["vehicle_position_z"]),
                )
                if (
                    previous is not None
                    and moved_meters > 1.0
                    and sample["grounded_wheel_count"] >= 3
                    and previous["grounded_wheel_count"] >= 3
                    and abs(
                        sample["vehicle_linear_velocity_y"]
                        - previous["vehicle_linear_velocity_y"]
                    )
                    <= 0.25
                ):
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    pytest.fail(
                        "Vehicle vertical motion did not settle after the Trip "
                        f"Overview resume; last sample={sample}"
                    )
                previous = sample
                await asyncio.sleep(0.02)

            maximum_vertical_rise = max(
                sample["vehicle_position_y"] - paused["vehicle_position_y"]
                for sample in samples
            )
            maximum_upward_velocity = max(
                sample["vehicle_linear_velocity_y"] for sample in samples
            )
            assert maximum_vertical_rise <= 2.0
            assert maximum_upward_velocity <= 5.0
            assert max(sample["angular_speed_radps"] for sample in samples) <= 5.0
        finally:
            await client.request("input.key", {"key": "W", "state": "release"})


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_chase_camera_damps_vehicle_yaw_and_keeps_a_level_horizon(
    tmp_path: Path,
) -> None:
    artifacts = _artifact_directory(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input", "screenshot"),
        transcript=artifacts / "chase-camera-damping.jsonl",
        log_path=artifacts / "chase-camera-damping-godot.log",
    )
    async with process as client:
        ready = (await client.describe("vehicle.input.conditioner"))["test_state"]
        assert ready["active_profile"] == "balanced"

        try:
            # Two separate budgets, because they bound different things. Getting
            # the throttle held through focus transitions is input latency, which
            # a loaded runner can stretch; accelerating to the probe speed once it
            # is held is vehicle behaviour. Sharing one budget let the first
            # consume the second, and this test failed on Windows CI having held
            # full throttle for about 0.12 s of its 7 s. Timing the acceleration
            # from when throttle actually engages keeps the assertion about the
            # vehicle rather than about the runner.
            input_state = await wait_for_key_conditioner(
                client,
                key="W",
                raw_field="raw_throttle",
                predicate=lambda current: (
                    current["conditioned_throttle"] > 0
                    and current["stationary_hold"] is False
                ),
                failure="Vehicle input did not reach the camera steering probe",
                timeout=8.0,
            )

            deadline = asyncio.get_running_loop().time() + 7.0
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                state = (await client.describe("camera.chase.rig"))["test_state"]
                if remaining <= 0:
                    pytest.fail(
                        "Vehicle did not reach the camera steering probe speed; "
                        f"speed_mps={state['speed_mps']}, "
                        f"input_state={input_state}"
                    )
                if state["speed_mps"] >= 8:
                    break
                # Keep holding the key: focus transitions can drop it, and the
                # conditioner falls back to zero throttle if the raw input stops.
                #
                # Bounded by whatever is left of the acceleration budget, and
                # skipped entirely once too little remains to re-establish the
                # hold. Clamping this up to a floor would let it run past the
                # deadline and report an input-hold failure where the real result
                # is that the vehicle did not reach the probe speed.
                if remaining > 0.5:
                    input_state = await wait_for_key_conditioner(
                        client,
                        key="W",
                        raw_field="raw_throttle",
                        predicate=lambda current: (
                            current["conditioned_throttle"] > 0
                            and current["stationary_hold"] is False
                        ),
                        failure="Vehicle input did not hold through the camera steering probe",
                        timeout=0.5,
                    )
                await asyncio.sleep(0.05)

            await client.request(
                "input.action", {"action": "steer_right", "state": "press"}
            )
            deadline = asyncio.get_running_loop().time() + 1.0
            max_heading_lag = 0.0
            while True:
                state = (await client.describe("camera.chase.rig"))["test_state"]
                heading_lag = state["heading_lag_degrees"]
                max_heading_lag = max(max_heading_lag, heading_lag)
                if heading_lag >= 45:
                    pytest.fail(f"Chase camera heading lag exceeded 45 degrees: {heading_lag}")
                # A qualifying sample settles the question even when it is the
                # one that arrived after the deadline: on a loaded runner the
                # describe round trip stretches, and the old order failed a
                # run whose last sample read 1.56 degrees.
                if 1 < heading_lag < 45:
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    pytest.fail(
                        "Chase camera did not exhibit measurable heading damping; "
                        f"maximum observed lag was {max_heading_lag} degrees"
                    )
                await asyncio.sleep(0.02)

            assert 1 < state["heading_lag_degrees"] < 45
            assert state["horizon_roll_degrees"] < 0.01
            assert state["inherits_vehicle_rotation"] is False
            screenshot = await client.screenshot(artifacts / "camera-steering.png")
            assert screenshot["bytes"] > 0
            # Hosted runners can cap the game window near 1024x576 even when the
            # project requests 1280x720. Verify a useful 16:9 capture without
            # coupling the camera behavior test to one desktop resolution.
            assert screenshot["width"] >= 960
            assert screenshot["height"] >= 540
            assert 1.7 <= screenshot["width"] / screenshot["height"] <= 1.85
        finally:
            await client.request(
                "input.action", {"action": "steer_right", "state": "release"}
            )
            await client.request("input.key", {"key": "W", "state": "release"})


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_read_only_session_rejects_input() -> None:
    process = PlayGodotProcess(REPO_ROOT, _route_package())
    async with process as client:
        with pytest.raises(PlayGodotError, match="CAPABILITY_DENIED"):
            await client.request("input.action", {"action": "accelerate", "state": "press"})


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_repeated_authentication_failures_trigger_bounded_cooldown(tmp_path: Path) -> None:
    async with _raw_server(tmp_path) as (host, port, token, _transcript):
        wrong_hello = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "session.hello",
                "params": {
                    "token": token + "wrong",
                    "protocol": "1.0",
                    "capabilities": ["read"],
                },
            },
            separators=(",", ":"),
        ).encode()
        for _attempt in range(5):
            rejected = await _raw_request(host, port, wrong_hello)
            assert rejected is not None
            assert rejected["error"]["name"] == "AUTH_FAILED"

        with pytest.raises((ConnectionError, ProtocolError)):
            await PlayGodotClient.connect(host, port, token=token, timeout=1)

        await asyncio.sleep(5.1)
        recovered = await PlayGodotClient.connect(host, port, token=token)
        assert await recovered.request("session.ping") == {"ok": True}
        await recovered.close(abort=True)


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_hostile_requests_fail_closed_and_are_transcribed(tmp_path: Path) -> None:
    async with _raw_server(_artifact_directory(tmp_path)) as (host, port, token, transcript):
        assert port > 0
        non_loopback = ""
        with (
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe,
            contextlib.suppress(OSError),
        ):
            probe.connect(("192.0.2.1", 9))
            non_loopback = probe.getsockname()[0]
        if non_loopback and not non_loopback.startswith("127."):
            with pytest.raises(OSError):
                await asyncio.wait_for(asyncio.open_connection(non_loopback, port), 0.5)

        wrong_hello = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 90,
                "method": "session.hello",
                "params": {"token": "wrong" * 8, "protocol": "1.0", "capabilities": ["read"]},
            },
            separators=(",", ":"),
        )
        valid_hello = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 91,
                "method": "session.hello",
                "params": {"token": token, "protocol": "1.0", "capabilities": ["read"]},
            },
            separators=(",", ":"),
        )
        privileged_read = '{"jsonrpc":"2.0","id":92,"method":"scene.current","params":{}}'
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(("\n".join((wrong_hello, valid_hello, privileged_read)) + "\n").encode())
        await writer.drain()
        pipelined = []
        while line := await asyncio.wait_for(reader.readline(), 2):
            pipelined.append(json.loads(line))
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.1)
        assert [response["error"]["name"] for response in pipelined] == ["AUTH_FAILED"]

        first_client = await _connect_after_session_cleanup(
            host,
            port,
            token=token,
            capabilities=("read", "input"),
        )
        initial_action_state = await first_client.describe("playgodot.fixture.action-state")
        assert initial_action_state["text"] == "released"
        await first_client.request("input.action", {"action": "ui_accept", "state": "press"})
        deadline = asyncio.get_running_loop().time() + 2.0
        while True:
            pressed_action_state = await first_client.describe("playgodot.fixture.action-state")
            if pressed_action_state["text"] == "pressed":
                break
            if asyncio.get_running_loop().time() >= deadline:
                pytest.fail("Injected action was not observed before the bounded deadline")
            await first_client.request("input.action", {"action": "ui_accept", "state": "press"})
            await asyncio.sleep(0.02)
        assert pressed_action_state["text"] == "pressed"
        abandoned_wait = asyncio.create_task(
            first_client.request(
                "signal.wait",
                {
                    "automation_id": "playgodot.fixture.button",
                    "signal": "pressed",
                    "timeout_ms": 2_000,
                },
            )
        )
        await asyncio.sleep(0)
        await first_client.close(abort=True)
        with contextlib.suppress(asyncio.CancelledError, ConnectionError, ProtocolError):
            await abandoned_wait
        await asyncio.sleep(0.1)

        second_client = await _connect_after_session_cleanup(host, port, token=token)
        # Session cleanup releases the abandoned action; wait for the fixture
        # to observe the release instead of sampling after a fixed sleep.
        released_action_state = await wait_for_describe(
            second_client,
            "playgodot.fixture.action-state",
            lambda state: state["text"] == "released",
            "Abandoned injected action was not released by session cleanup",
        )
        assert released_action_state["text"] == "released"
        capacity_results = await asyncio.gather(
            *(
                second_client.request(
                    "signal.wait",
                    {
                        "automation_id": "playgodot.fixture.button",
                        "signal": "pressed",
                        "timeout_ms": 20,
                    },
                )
                for _wait in range(8)
            ),
            return_exceptions=True,
        )
        assert all(
            isinstance(result, PlayGodotError) and result.name == "TIMEOUT"
            for result in capacity_results
        )
        assert await second_client.request("session.ping") == {"ok": True}
        await second_client.close(abort=True)
        await asyncio.sleep(0.1)

        unauthenticated = await _raw_request(
            host,
            port,
            b'{"jsonrpc":"2.0","id":1,"method":"scene.current","params":{}}',
        )
        assert unauthenticated["error"]["name"] == "AUTH_REQUIRED"

        malformed = await _raw_request(host, port, b"not-json")
        assert malformed["error"]["name"] == "PARSE_ERROR"

        wrong_token = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session.hello",
                "params": {"token": token + "wrong", "protocol": "1.0", "capabilities": ["read"]},
            },
            separators=(",", ":"),
        ).encode()
        rejected = await _raw_request(host, port, wrong_token)
        assert rejected["error"]["name"] == "AUTH_FAILED"

        oversized = await _raw_request(host, port, b"x" * 65_537, allow_empty=True)
        assert oversized is None or oversized["error"]["name"] == "LIMIT_EXCEEDED"

    outcomes = {json.loads(line)["outcome"] for line in transcript.read_text().splitlines()}
    assert {"auth_required", "parse_error", "auth_failed"} <= outcomes
    # The capacity probe must not pass by timing out phantom, unconnected waits.
    assert "already connected" not in (_artifact_directory(tmp_path) / "raw-godot.log").read_text()


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_owned_quit_capability_and_connection_only_close(tmp_path: Path) -> None:
    artifacts = _artifact_directory(tmp_path) / "owned-quit-grants"
    async with _raw_server(artifacts) as (host, port, token, transcript):
        unauthenticated = await _raw_request(
            host, port, b'{"jsonrpc":"2.0","id":1,"method":"session.quit","params":{}}',
        )
        assert unauthenticated["error"]["name"] == "AUTH_REQUIRED"
        client = await _connect_after_session_cleanup(host, port, token=token)
        capabilities = await client.request("session.capabilities")
        assert capabilities["granted"] == ["read"]
        with pytest.raises(PlayGodotError) as denied:
            await client.request("session.quit")
        assert denied.value.name == "CAPABILITY_DENIED"
        assert await client.request("session.ping") == {"ok": True}
        await client.close()
        # Close releases only the connection; the same endpoint still serves
        # a new ordinary client without adding the owner's shutdown grant.
        client = await _connect_after_session_cleanup(host, port, token=token)
        assert await client.request("session.ping") == {"ok": True}
        await client.close()
        owner = await _connect_after_session_cleanup(
            host, port, token=token, capabilities=("shutdown",),
        )
        for parameters in ({"exit_code": 1}, {"unexpected": True}):
            with pytest.raises(PlayGodotError) as malformed:
                await owner.request("session.quit", parameters)
            assert malformed.value.name == "INVALID_PARAMS"
            assert await owner.request("session.ping") == {"ok": True}
        await owner.close()
    result = json.loads((artifacts / "raw-godot.shutdown.json").read_text())
    assert result["status"] == "native-observation" and result["exit_status"] == 0
    assert result["owner_finalization_required"]
    assert result["quit_acknowledged"] and result["output_eof"] and not result["fallback"]
    assert not result["diagnostics"]
    assert token not in transcript.read_text() and token not in json.dumps(result)


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect_without_reading", [False, True])
async def test_authorized_quit_releases_pending_resources_and_exits_zero(
    tmp_path: Path, disconnect_without_reading: bool,
) -> None:
    artifacts = _artifact_directory(tmp_path) / (
        "owned-quit-peer-loss" if disconnect_without_reading else "owned-quit-resources"
    )
    async with _raw_server(artifacts) as (host, port, token, _transcript):
        client = await _connect_after_session_cleanup(
            host, port, token=token, capabilities=("read", "input", "shutdown"),
        )
        await client.request("input.action", {"action": "ui_accept", "state": "press"})
        pending = asyncio.create_task(client.request("signal.wait", {
            "automation_id": "playgodot.fixture.button", "signal": "pressed", "timeout_ms": 5_000,
        }))
        # A subsequent correlated response is a wire-order barrier: the server
        # has processed the earlier wait before accepting the quit request.
        await asyncio.sleep(0)
        assert await client.request("session.ping") == {"ok": True}
        if disconnect_without_reading:
            # Use this owned session's next valid ID, with no client future:
            # the peer abandons the response immediately after sending quit.
            payload = {"jsonrpc": "2.0", "id": client._next_id,
                       "method": "session.quit", "params": {}}
            client._writer.write((json.dumps(payload) + "\n").encode())
            await client._writer.drain()
            client._writer.close()
        else:
            assert await client.request("session.quit") == {"quitting": True}
        with pytest.raises((ProtocolError, ConnectionError)):
            await pending
        await client.close(abort=True)
    result = json.loads((artifacts / "raw-godot.shutdown.json").read_text())
    assert result["status"] == "native-observation" and result["exit_status"] == 0
    assert result["owner_finalization_required"]
    assert result["output_eof"] and not result["fallback"] and not result["diagnostics"]
    assert result["quit_cleanup"] == {
        "pending_waits_before": 1, "held_inputs_before": 1,
        "pending_waits_after": 0, "held_inputs_after": 0,
    }


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_concurrent_signal_waits_all_receive_one_native_emission(tmp_path: Path) -> None:
    artifacts = _artifact_directory(tmp_path) / "signal-all-eight"
    process = PlayGodotProcess(
        REPO_ROOT, _route_package(), capabilities=("read", "input"),
        transcript=artifacts / "requests.jsonl", log_path=artifacts / "godot.log",
    )
    async with process as client:
        async with asyncio.TaskGroup() as group:
            waits = [group.create_task(client.request("signal.wait", {
                "automation_id": "playgodot.fixture.button", "signal": "pressed",
                "timeout_ms": 2_000,
            })) for _ in range(8)]
            await asyncio.sleep(0)
            # This response is a wire-order barrier after the eight wait requests.
            assert await client.request("session.ping") == {"ok": True}
            with pytest.raises(PlayGodotError, match="BUSY"):
                await client.request("signal.wait", {
                    "automation_id": "playgodot.fixture.button", "signal": "pressed",
                    "timeout_ms": 2_000,
                })
            await client.request("input.click", {"automation_id": "playgodot.fixture.button"})
            assert await asyncio.gather(*waits) == [{"signal": "pressed"}] * 8
        # One-shot callbacks cannot produce stale duplicate responses on another click.
        await client.request("input.click", {"automation_id": "playgodot.fixture.button"})
        assert await client.request("session.ping") == {"ok": True}
    entries = [json.loads(line) for line in (artifacts / "requests.jsonl").read_text().splitlines()]
    successes = [row for row in entries if row["method"] == "signal.wait"
                 and row["outcome"] == "success"]
    assert len(successes) == len({row["request_id"] for row in successes}) == 8
    assert process.teardown_result["status"] == "passed"
    assert not process.teardown_result["diagnostics"]


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_signal_timeout_does_not_disconnect_another_pending_wait(tmp_path: Path) -> None:
    artifacts = _artifact_directory(tmp_path) / "signal-staggered"
    process = PlayGodotProcess(
        REPO_ROOT, _route_package(), capabilities=("read", "input"),
        transcript=artifacts / "requests.jsonl", log_path=artifacts / "godot.log",
    )
    async with process as client:
        long_wait = asyncio.create_task(client.request("signal.wait", {
            "automation_id": "playgodot.fixture.button", "signal": "pressed", "timeout_ms": 2_000,
        }))
        await asyncio.sleep(0)
        short_wait = asyncio.create_task(client.request("signal.wait", {
            "automation_id": "playgodot.fixture.button", "signal": "pressed", "timeout_ms": 20,
        }))
        try:
            await asyncio.sleep(0)
            assert await client.request("session.ping") == {"ok": True}
            with pytest.raises(PlayGodotError, match="TIMEOUT"):
                await short_wait
            assert not long_wait.done()
            await client.request("input.click", {"automation_id": "playgodot.fixture.button"})
            assert await long_wait == {"signal": "pressed"}
        finally:
            for task in (long_wait, short_wait):
                if not task.done():
                    task.cancel()
            await asyncio.gather(long_wait, short_wait, return_exceptions=True)
    entries = [json.loads(line) for line in (artifacts / "requests.jsonl").read_text().splitlines()]
    waits = [row for row in entries if row["method"] == "signal.wait"]
    assert sorted(row["outcome"] for row in waits) == ["success", "timeout"]
    assert len({row["request_id"] for row in waits}) == 2
    assert process.teardown_result["status"] == "passed"
    assert not process.teardown_result["diagnostics"]


_SIGNAL_NATIVE_HARNESS = '''extends "res://server.gd"
var replies: Array[Dictionary] = []
var outcomes: Array[Dictionary] = []
func _ready() -> void:
    _id_regex.compile(TARGET_ID_PATTERN)
    set_process(false)
func _send(response: Dictionary) -> void:
    replies.append(response.duplicate(true))
func _record(id: Variant, method: String, outcome: String, _started: int) -> void:
    outcomes.append({"id": id, "method": method, "outcome": outcome})
'''

_SIGNAL_NATIVE_CONTROL = '''extends Node
func _ready() -> void:
    call_deferred("run")
func run() -> void:
    var target = Node.new()
    target.add_user_signal("ping")
    target.set_meta("automation_id", "signal.fixture")
    add_child(target)
    var server = load("res://harness.gd").new()
    add_child(server)
    var mode := "__MODE__"
    var returned = server._signal_wait({"automation_id": "signal.fixture",
        "signal": "ping", "timeout_ms": 20}, 1)
    if mode == "freed-disconnect":
        server._signal_wait({"automation_id": "signal.fixture",
            "signal": "ping", "timeout_ms": 500}, 2)
    var connections := target.get_signal_connection_list("ping").size()
    target.free()
    if mode == "freed-timeout":
        var deadline := Time.get_ticks_msec() + 30
        while Time.get_ticks_msec() < deadline:
            await get_tree().process_frame
        server._poll_pending_signals()
    elif mode == "freed-disconnect":
        server._clear_connection()
    var output := {"mode": mode, "returned": returned, "connections_before_free": connections,
        "pending": server._pending_signals.keys(), "results": server._signal_results.keys(),
        "replies": server.replies.duplicate(true), "outcomes": server.outcomes.duplicate(true)}
    server._clear_connection()
    server.free()
    print("PLAYGODOT_SIGNAL_CONTROL " + JSON.stringify(output))
    get_tree().quit(0)
'''


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.parametrize("mode", ["freed-timeout", "freed-disconnect", "connect-failure"])
def test_signal_wait_native_lifetime_and_connection_failure(tmp_path: Path, mode: str) -> None:
    """Actual copied server methods/native signals; no game, renderer or remote invoke API."""
    artifacts = _artifact_directory(tmp_path) / f"signal-native-{mode}"
    fixture = artifacts / "fixture"
    fixture.mkdir(parents=True)
    source = (REPO_ROOT / "addons/playgodot/server.gd").read_bytes()
    candidate = source
    if mode == "connect-failure":
        needle = b"var callback := func(): _on_pending_signal(key)"
        assert candidate.count(needle) == 1
        # Deliberately invalid native callable: connect must fail before reservation.
        candidate = candidate.replace(needle, b"var callback := Callable()")
    (fixture / "server.gd").write_bytes(candidate)
    (fixture / "harness.gd").write_text(_SIGNAL_NATIVE_HARNESS, encoding="utf-8")
    (fixture / "control.gd").write_text(
        _SIGNAL_NATIVE_CONTROL.replace("__MODE__", mode), encoding="utf-8",
    )
    (fixture / "project.godot").write_text(
        'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n', encoding="utf-8",
    )
    (fixture / "main.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" path="res://control.gd" id="1"]\n'
        '[node name="SignalControl" type="Node"]\nscript = ExtResource("1")\n', encoding="utf-8",
    )
    executable = PlayGodotProcess._godot_from_environment().resolve()
    if executable.name.endswith("_console.exe"):
        # A timeout must own/kill the actual engine, not leave its console child alive.
        executable = executable.with_name(executable.name.replace("_console.exe", ".exe"))
    assert executable.is_file()
    argv = [str(executable), "--headless", "--audio-driver", "Dummy", "--path", str(fixture)]
    started = time.monotonic()
    try:
        result = subprocess.run(argv, capture_output=True, timeout=15, check=False)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = 124, error.stdout or b"", error.stderr or b""
    (artifacts / "stdout.log").write_bytes(stdout)
    (artifacts / "stderr.log").write_bytes(stderr)
    (artifacts / "command.json").write_text(json.dumps({
        "argv": argv, "exit_status": code, "elapsed_seconds": time.monotonic() - started,
        "timeout_seconds": 15, "timeout_kills_direct_engine": code == 124,
        "engine_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "fixture_server_sha256": hashlib.sha256(candidate).hexdigest(),
        "environment": {key: os.environ.get(key) for key in (
            "DOTNET_ROLL_FORWARD", "DOTNET_GCgen0size", "HOME", "APPDATA", "LOCALAPPDATA",
        )},
    }, indent=2) + "\n", encoding="utf-8")
    assert code == 0, stderr.decode(errors="replace")
    assert b"Godot Engine v4.7.1.stable.mono.official." in stdout
    records = [json.loads(line.removeprefix("PLAYGODOT_SIGNAL_CONTROL "))
               for line in stdout.decode().splitlines()
               if line.startswith("PLAYGODOT_SIGNAL_CONTROL ")]
    assert len(records) == 1
    record = records[0]
    assert record["mode"] == mode and record["pending"] == record["results"] == []
    if mode == "connect-failure":
        assert record["returned"]["error"]["name"] == "INTERNAL_ERROR"
        assert record["returned"]["error"]["code"] == -32603
        assert record["connections_before_free"] == 0 and not record["replies"]
        # This one native error is the declared negative, never a production log filter.
        errors = [line for line in stderr.decode().splitlines() if line.startswith("ERROR:")]
        assert errors == ["ERROR: Cannot connect to 'ping': the provided callable is null."]
        assert b"SCRIPT ERROR:" not in stderr
    else:
        assert not stderr, stderr.decode(errors="replace")
        assert record["returned"] == {"pending": True}
        if mode == "freed-timeout":
            assert record["connections_before_free"] == 1
            assert len(record["replies"]) == 1
            assert record["replies"][0]["error"]["name"] == "TIMEOUT"
        else:
            assert record["connections_before_free"] == 2 and not record["replies"]
            assert record["outcomes"] == [
                {"id": number, "method": "signal.wait", "outcome": "cancelled"}
                for number in (1, 2)
            ]
