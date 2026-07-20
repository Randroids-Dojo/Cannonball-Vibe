from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import signal
import socket
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO

import pytest
from PIL import Image

from cannonball_playgodot import (
    PlayGodotClient,
    PlayGodotError,
    PlayGodotProcess,
    ProtocolError,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MAX_RAW_LOG_BYTES = 2_000_000


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
    token = "integration-test-token-0123456789abcdef"
    transcript = tmp_path / "hostile.jsonl"
    runtime_log = tmp_path / "raw-godot.log"
    environment = os.environ.copy()
    environment.update(
        PLAYGODOT_TOKEN=token,
        PLAYGODOT_CAPABILITIES="read,input,screenshot",
        PLAYGODOT_TRANSCRIPT=str(transcript),
    )
    command = [
        environment["GODOT_BIN"],
        "--audio-driver",
        "Dummy",
        "--rendering-method",
        "gl_compatibility",
        "--path",
        str(REPO_ROOT),
        "addons/playgodot/bootstrap.tscn",
        "--",
        "--playgodot",
        f"--route-package={_route_package()}",
    ]
    if platform.system() == "Linux" and os.environ.get("PLAYGODOT_XVFB") == "1":
        command = ["xvfb-run", "-a", *command]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=environment,
        start_new_session=os.name == "posix",
    )
    assert process.stdout is not None
    drain_task: asyncio.Task[None] | None = None
    log = runtime_log.open("wb")
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 20
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("Godot did not become ready within 20 seconds")
            line = await asyncio.wait_for(process.stdout.readline(), remaining)
            if not line:
                raise RuntimeError("Godot exited before the hostile-input fixture was ready")
            _write_bounded_log(log, line)
            decoded = line.decode(errors="replace").rstrip()
            if decoded.startswith("PLAYGODOT_READY "):
                ready = json.loads(decoded.removeprefix("PLAYGODOT_READY "))
                drain_task = asyncio.create_task(_drain_process_output(process.stdout, log))
                yield ready["address"], ready["port"], token, transcript
                break
    finally:
        with contextlib.suppress(ProcessLookupError):
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()
        if drain_task is not None:
            await drain_task
        log.close()


async def _drain_process_output(stream: asyncio.StreamReader, log: BinaryIO) -> None:
    while line := await stream.readline():
        _write_bounded_log(log, line)


def _write_bounded_log(log: BinaryIO, line: bytes) -> None:
    remaining = MAX_RAW_LOG_BYTES - log.tell()
    if remaining > 0:
        log.write(line[:remaining])
        log.flush()


async def _raw_request(host: str, port: int, payload: bytes) -> dict | None:
    for attempt in range(3):
        reader, writer = await asyncio.open_connection(host, port)
        try:
            writer.write(payload + b"\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), 2)
            return json.loads(line) if line else None
        except ConnectionResetError:
            if attempt == 2:
                raise
            await asyncio.sleep(0.1)
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            await asyncio.sleep(0.05)
    raise AssertionError("raw request retry loop exhausted")


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
        await client.request("input.action", {"action": "toggle_camera", "state": "press"})
        await asyncio.sleep(0.05)
        await client.request("input.action", {"action": "toggle_camera", "state": "release"})
        await asyncio.sleep(0.05)
        assert (await client.describe("camera.chase.rig"))["test_state"]["active"] is False
        assert (await client.describe("camera.cockpit.view"))["test_state"]["active"] is True
        await client.request("input.action", {"action": "toggle_camera", "state": "press"})
        await asyncio.sleep(0.05)
        await client.request("input.action", {"action": "toggle_camera", "state": "release"})
        await asyncio.sleep(0.05)
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
            "button_count": 3,
            "open": True,
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
            "button_count": 3,
            "open": False,
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
        await client.request(
            "input.action", {"action": "toggle_trip_map", "state": "press"}
        )
        await asyncio.sleep(0.05)
        await client.request(
            "input.action", {"action": "toggle_trip_map", "state": "release"}
        )
        assert (await wait_for_trip_map)["signal"] == "visibility_changed"

        trip_map = await client.describe("trip-map.root")
        assert trip_map["visible"] is True
        assert trip_map["test_state"]["open"] is True
        assert trip_map["test_state"]["simulation_paused"] is True
        assert trip_map["test_state"]["distance_remaining_m"] > 0
        assert trip_map["test_state"]["feature_count"] >= 0
        summary = await client.describe("trip-map.summary")
        assert "mi completed" in summary["text"]
        assert "mi remaining" in summary["text"]
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
async def test_chase_camera_damps_vehicle_yaw_and_keeps_a_level_horizon(
    tmp_path: Path,
) -> None:
    artifacts = _artifact_directory(tmp_path)
    process = PlayGodotProcess(
        REPO_ROOT,
        _route_package(),
        capabilities=("read", "input", "screenshot"),
        transcript=artifacts / "camera-handling.jsonl",
        log_path=artifacts / "camera-handling-godot.log",
    )
    async with process as client:
        await client.request("input.action", {"action": "accelerate", "state": "press"})
        try:
            deadline = asyncio.get_running_loop().time() + 2.0
            while True:
                state = (await client.describe("camera.chase.rig"))["test_state"]
                if state["speed_mps"] >= 8:
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    pytest.fail("Vehicle did not reach the camera steering probe speed")
                await asyncio.sleep(0.05)

            await client.request(
                "input.action", {"action": "steer_right", "state": "press"}
            )
            await asyncio.sleep(0.25)
            state = (await client.describe("camera.chase.rig"))["test_state"]
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
            await client.request(
                "input.action", {"action": "accelerate", "state": "release"}
            )


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
        await asyncio.sleep(0.05)
        pressed_action_state = await first_client.describe("playgodot.fixture.action-state")
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
        await asyncio.sleep(0.25)
        released_action_state = await second_client.describe("playgodot.fixture.action-state")
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

        oversized = await _raw_request(host, port, b"x" * 65_537)
        assert oversized is None or oversized["error"]["name"] == "LIMIT_EXCEEDED"

    outcomes = {json.loads(line)["outcome"] for line in transcript.read_text().splitlines()}
    assert {"auth_required", "parse_error", "auth_failed"} <= outcomes
