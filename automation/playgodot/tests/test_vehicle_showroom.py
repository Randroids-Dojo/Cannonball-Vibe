from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from cannonball_playgodot import PlayGodotClient, PlayGodotProcess

from .input_support import wait_for_conditioner, wait_for_describe

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT = "showroom.root"
PANEL = "vehicle.inspection.panel"
OPENINGS = {
    "Door_FL": -62.0,
    "Door_FR": 62.0,
    "Door_RL": -58.0,
    "Door_RR": 58.0,
    "Hood_Hinge": 68.0,
    "Trunk_Hinge": -72.0,
}
VIEWS = (
    "overview", "front", "rear", "left", "right", "top", "underside",
    "cockpit", "rear-cabin", "engine", "luggage",
)
LOWER_VIEWS = {"overview", "cockpit", "rear-cabin", "engine", "luggage"}
PARKED_RUN_FIELDS = (
    "restart_count", "seed", "cash", "selected_asset", "route_distance_m", "edge_distance_m",
    "vehicle_position_x", "vehicle_position_y", "vehicle_position_z",
    "vehicle_linear_velocity_x", "vehicle_linear_velocity_y", "vehicle_linear_velocity_z",
    "camera_mode", "assist_profile", "vehicle_setup", "forward_speed_cap_mph",
)
METRIC_FIELDS = (
    "metrics_elapsed_seconds", "frame_p50_ms", "frame_p95_ms", "frame_p99_ms", "frame_max_ms",
    "process_working_set_high_mib", "engine_static_high_mib", "render_video_high_mib",
    "viewport_draw_calls_high", "viewport_shadow_draw_calls_high", "viewport_primitives_high",
)


async def _key(client: PlayGodotClient, key: str) -> None:
    for state in ("press", "release"):
        await client.request("input.key", {"key": key, "state": state})


async def _joy_button(client: PlayGodotClient, button: str) -> None:
    for state in ("press", "release"):
        await client.request(
            "input.joypad_button", {"button": button, "state": state, "device": 0},
        )


async def _controller_focus(client: PlayGodotClient, target: str) -> list[str | None]:
    sequence: list[str | None] = []
    tried: set[tuple[str | None, str]] = set()
    for _ in range(64):
        focused = await client.request("ui.focused")
        identity = focused["automation_id"] if focused is not None else None
        sequence.append(identity)
        if identity == target:
            return sequence
        if focused is None:
            direction = "dpad_down"
        else:
            wanted = (await client.describe(target))["bounds"]
            current = focused["bounds"]
            dx = wanted["x"] + wanted["width"] / 2 - current["x"] - current["width"] / 2
            dy = wanted["y"] + wanted["height"] / 2 - current["y"] - current["height"] / 2
            horizontal = "dpad_right" if dx > 0 else "dpad_left"
            vertical = "dpad_down" if dy > 0 else "dpad_up"
            directed = [horizontal, vertical] if abs(dx) > abs(dy) else [vertical, horizontal]
            choices = list(dict.fromkeys([
                *directed, "dpad_up", "dpad_right", "dpad_down", "dpad_left",
            ]))
            direction = next(
                (value for value in choices if (identity, value) not in tried), choices[0],
            )
        tried.add((identity, direction))
        sequence.append("input:" + direction)
        await _joy_button(client, direction)
    pytest.fail(f"Controller navigation did not reach {target}: {sequence}")


async def _click(client: PlayGodotClient, automation_id: str) -> None:
    clip_id = None
    if automation_id == "vehicle.inspection.showroom":
        clip_id = "vehicle.inspection.window"
    elif automation_id.startswith("showroom.") and automation_id not in {
        "showroom.view." + view for view in LOWER_VIEWS
    }:
        clip_id = "showroom.controls"
    if clip_id is not None:
        for _ in range(64):
            control = await client.describe(automation_id)
            clip = (await client.describe(clip_id))["bounds"]
            bounds = control["bounds"]
            center = (bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
            if (clip["x"] <= center[0] <= clip["x"] + clip["width"]
                    and clip["y"] <= center[1] <= clip["y"] + clip["height"]):
                break
            await _key(client, "Tab")
        else:
            pytest.fail(f"Keyboard focus could not reveal {automation_id} inside {clip_id}")
    control = await client.describe(automation_id)
    assert control["visible"] and control["enabled"], control
    assert control["bounds"]["width"] > 0 and control["bounds"]["height"] > 0, control
    await client.request("input.click", {"automation_id": automation_id})


async def _state(
    client: PlayGodotClient, predicate: Callable[[dict], bool], reason: str,
) -> dict:
    description = await wait_for_describe(
        client, ROOT, lambda value: predicate(value["test_state"]), reason, timeout=10,
    )
    state = description["test_state"]
    assert len(state) + 1 <= 64, "Showroom state exceeded the existing bridge value budget"
    assert state["asset_id"] == "endurance-sedan" and state["body_frozen"] is True
    assert state["private_world"] is True and state["run_paused"] is True
    assert state["display_speed_mps"] == 0
    for name in ("camera_x", "camera_y", "camera_z", "yaw", "pitch", "distance"):
        assert isinstance(state[name], int | float) and not isinstance(state[name], bool)
        assert math.isfinite(state[name]), (name, state[name])
    assert state["distance"] > 0
    return state


def _openings_match(state: dict, opened: set[str]) -> bool:
    return all(
        state["opening_" + name] is (name in opened)
        and math.isclose(
            state["angle_" + name], angle if name in opened else 0.0,
            rel_tol=0, abs_tol=0.1,
        )
        for name, angle in OPENINGS.items()
    )


def _write_observations(path: Path, observations: list[dict]) -> None:
    path.write_text(json.dumps(observations, indent=2, allow_nan=False) + "\n", encoding="utf-8")


async def _measured_case(client: PlayGodotClient, case: str) -> dict:
    state = await _state(
        client, lambda value: value["metrics_case"] == case
        and value["metrics_elapsed_seconds"] >= 1.0
        and value["metrics_samples"] >= 10 and value["frame_p50_ms"] > 0,
        f"The actual {case} frame observer did not complete a post-warmup diagnostic window",
    )
    assert state["metrics_warmup_seconds"] == 2
    assert state["metrics_overflow"] is False
    assert isinstance(state["metrics_samples"], int)
    assert not isinstance(state["metrics_samples"], bool)
    for name in METRIC_FIELDS:
        assert isinstance(state[name], int | float) and not isinstance(state[name], bool)
        assert math.isfinite(state[name]) and state[name] >= 0, (name, state[name])
    assert 0 < state["frame_p50_ms"] <= state["frame_p95_ms"] <= state["frame_p99_ms"]
    assert state["frame_p99_ms"] <= state["frame_max_ms"]
    assert state["process_working_set_high_mib"] > 0
    return state


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_vehicle_showroom_controls_and_modal_return(tmp_path: Path) -> None:
    """Operate the real parked viewer and retain its actual camera/joint and return states."""
    package_root = REPO_ROOT / ".tools/scenarios/official-corridor"
    pointer = json.loads((package_root / "current-package.json").read_text())
    artifacts = Path(os.environ.get("PLAYGODOT_ARTIFACT_DIR", str(tmp_path)))
    artifacts.mkdir(parents=True, exist_ok=True)
    observation_path = artifacts / "showroom-observations.json"
    observations: list[dict] = []
    images: list[dict] = []
    rendering_method = os.environ.get("PLAYGODOT_SHOWROOM_RENDERER", "gl_compatibility")
    raw_size = os.environ.get("PLAYGODOT_SHOWROOM_SIZE")
    window_size = None
    if raw_size is not None:
        matched = re.fullmatch(r"([0-9]+)x([0-9]+)", raw_size)
        if matched is None:
            raise ValueError("PLAYGODOT_SHOWROOM_SIZE must be integer widthxheight")
        window_size = tuple(int(value) for value in matched.groups())
    process = PlayGodotProcess(
        REPO_ROOT, package_root / pointer["root_relative_path"],
        vehicle="endurance-sedan", isolate_user_data=True,
        capabilities=("read", "input", "screenshot"), startup_timeout=60, request_timeout=30,
        transcript=artifacts / "showroom.jsonl", log_path=artifacts / "showroom-godot.log",
        rendering_method=rendering_method,
        window_size=window_size,
    )
    isolated: Path | None = None

    def record(stage: str, **values: object) -> None:
        observations.append({"stage": stage, **values})
        _write_observations(observation_path, observations)

    async def capture(name: str) -> None:
        path = artifacts / f"showroom-{name}.png"
        image = await client.screenshot(path)
        assert image["bytes"] > 0 and image["width"] >= 960 and image["height"] >= 540
        assert hashlib.sha256(path.read_bytes()).hexdigest() == image["sha256"]
        images.append({"path": str(path), **image})
        record("image-" + name, image=images[-1])

    try:
        async with asyncio.timeout(240), process as client:
            initial = (await client.describe(PANEL))["test_state"]
            assert initial["selected_asset"] == "endurance-sedan" and initial["open"] is False
            assert process._runtime_directory is not None
            isolated = process._runtime_directory.resolve()
            user_data = Path(initial["user_data_directory"]).resolve()
            assert user_data.is_relative_to(isolated), "Viewer tests must isolate player files"
            await wait_for_describe(
                client, "run.session",
                lambda value: value["test_state"]["linear_speed_mps"] <= 0.5
                and value["test_state"]["grounded_wheel_count"] == 4,
                "The actual sedan did not settle within the parked inspection guard", timeout=10,
            )
            await _key(client, "F2")
            original_panel = await wait_for_describe(
                client, PANEL,
                lambda value: value["test_state"]["open"] and value["test_state"]["body_frozen"],
                "F2 did not open the original parked inspection panel", timeout=10,
            )
            await _click(client, "vehicle.inspection.showroom")
            opened = await _state(
                client, lambda value: value["view"] == "overview" and value["ui_visible"]
                and value["rendered_frames"] > 0,
                "The showroom did not open with its actual overview camera",
            )
            assert opened["renderer"] == rendering_method
            assert opened["viewport_width"] >= 960 and opened["viewport_height"] >= 540
            if window_size is not None:
                assert (opened["viewport_width"], opened["viewport_height"]) == window_size
            # Main refreshes this snapshot at entry, after the parked body freezes.
            # Its process is disabled while the modal is active; later return
            # verification therefore requires a newly refreshed Main sample.
            parked = (await client.describe("run.session"))["test_state"]
            record("entered", viewer=opened, parked=parked,
                   original_panel=original_panel["test_state"],
                   initial_focus=await client.request("ui.focused"))
            await capture("entry-overview")
            await _click(client, "showroom.close-all")
            await _state(client, lambda value: _openings_match(value, set()), "Initial hinges open")

            for name in OPENINGS:
                control = "showroom.opening." + name.lower().replace("_", "-")
                await _click(client, control)
                actual = await _state(
                    client, lambda value, selected=name: _openings_match(value, {selected}),
                    f"{name} did not independently reach its signed native angle",
                )
                record("independent-open-" + name, viewer=actual)
                await _click(client, control)
                await _state(
                    client, lambda value: _openings_match(value, set()),
                    f"{name} failed to return to its original closed angle",
                )
            await _click(client, "showroom.open-all")
            actual = await _state(
                client, lambda value: _openings_match(value, set(OPENINGS)),
                "Open-all did not reach all six existing native hinge angles",
            )
            record("all-open", viewer=actual)
            await capture("all-open")
            await _click(client, "showroom.close-all")
            await _state(
                client, lambda value: _openings_match(value, set()), "Close-all left a hinge open",
            )

            camera_positions: dict[str, tuple[float, ...]] = {}
            for view in VIEWS:
                await _click(client, "showroom.view." + view)
                # Focus/reveal requests may advance many frames before the
                # actual click. Establish this barrier after the action; a
                # synchronous new label can still accompany the previous pose.
                preceding_frame = (await client.describe(ROOT))["test_state"]["rendered_frames"]
                actual = await _state(
                    client, lambda value, selected=view, before=preceding_frame:
                    value["view"] == selected and value["rendered_frames"] > before + 1,
                    f"The {view} camera preset did not become active",
                )
                camera_positions[view] = tuple(actual["camera_" + axis] for axis in "xyz")
                record("view-" + view, viewer=actual)
                if view == "underside":
                    assert actual["floor_visible"] is False, "Floor obscures underbody inspection"
                if view == "engine":
                    await _state(
                        client,
                        lambda value: value["opening_Hood_Hinge"]
                        and abs(value["angle_Hood_Hinge"] - OPENINGS["Hood_Hinge"]) <= 0.1,
                        "Engine preset did not open the actual hood",
                    )
                if view == "luggage":
                    await _state(
                        client,
                        lambda value: value["opening_Trunk_Hinge"]
                        and abs(value["angle_Trunk_Hinge"] - OPENINGS["Trunk_Hinge"]) <= 0.1,
                        "Luggage preset did not open the actual trunk",
                    )
                measured = await _measured_case(client, view + ":studio")
                record("metrics-view-" + view, viewer=measured)
                await capture("view-" + view)
            assert len(set(camera_positions.values())) == len(VIEWS), (
                "Different preset labels must select distinct actual camera positions"
            )
            assert camera_positions["left"][0] * camera_positions["right"][0] < 0
            assert camera_positions["front"][2] * camera_positions["rear"][2] < 0
            assert camera_positions["top"][1] > camera_positions["overview"][1]
            assert camera_positions["underside"][1] < 0, "Underside camera stayed above the floor"

            await _click(client, "showroom.view.overview")
            before_orbit = await _state(
                client, lambda value: not value["auto_orbit"], "Orbit active",
            )
            await _click(client, "showroom.orbit")
            orbit = await _state(
                client, lambda value: value["auto_orbit"]
                and abs(value["yaw"] - before_orbit["yaw"]) > 0.03,
                "Automatic orbit changed its toggle without moving the camera",
            )
            assert any(abs(orbit["camera_" + axis] - before_orbit["camera_" + axis]) > 0.01
                       for axis in "xz")
            record("automatic-orbit", before=before_orbit, after=orbit)
            await _click(client, "showroom.orbit")
            await _state(client, lambda value: not value["auto_orbit"], "Orbit did not stop")

            for key, field, minimum_change in (
                ("L", "yaw", 0.04), ("I", "pitch", 0.04),
                ("W", "target_y", 0.02), ("D", "target_x", 0.02),
                ("Equal", "distance", 0.1),
            ):
                before = (await client.describe(ROOT))["test_state"]
                await client.request("input.key", {"key": key, "state": "press"})
                try:
                    moved = await _state(
                        client, lambda value, name=field, prior=before[field], delta=minimum_change:
                        abs(value[name] - prior) > delta,
                        f"Physical {key} input did not move {field}",
                    )
                finally:
                    await client.request("input.key", {"key": key, "state": "release"})
                record("keyboard-" + field, before=before, after=moved)
            for axis, field, minimum_change in (
                ("right_x", "yaw", 0.04), ("trigger_right", "distance", 0.1),
            ):
                before = (await client.describe(ROOT))["test_state"]
                await client.request(
                    "input.joypad_motion", {"axis": axis, "value": 0.7, "device": 0},
                )
                try:
                    moved = await _state(
                        client, lambda value, name=field, prior=before[field], delta=minimum_change:
                        abs(value[name] - prior) > delta,
                        f"Physical controller {axis} input did not move {field}",
                    )
                finally:
                    await client.request(
                        "input.joypad_motion", {"axis": axis, "value": 0, "device": 0},
                    )
                record("controller-" + field, before=before, after=moved)
            await _key(client, "R")
            await _state(
                client, lambda value: value["view"] == "overview"
                and abs(value["distance"] - opened["distance"]) < 0.001
                and abs(value["target_y"] - opened["target_y"]) < 0.001,
                "Reset did not restore the original overview distance and target",
            )
            await client.request("input.key", {"key": "Equal", "state": "press"})
            try:
                minimum_zoom = await _state(
                    client, lambda value: value["distance"] <= 0.7001,
                    "Exterior zoom did not reach its declared minimum",
                )
            finally:
                await client.request("input.key", {"key": "Equal", "state": "release"})
            barrier = minimum_zoom["rendered_frames"]
            minimum_zoom = await _state(
                client, lambda value: value["rendered_frames"] > barrier + 2,
                "Minimum zoom did not render",
            )
            record("exterior-minimum-zoom", viewer=minimum_zoom)
            actual_distance_from_target = math.dist(
                [minimum_zoom["camera_" + axis] for axis in "xyz"],
                [minimum_zoom["target_" + axis] for axis in "xyz"],
            )
            required_radial_distance = minimum_zoom["camera_clearance_m"]
            assert math.isfinite(required_radial_distance)
            assert required_radial_distance > minimum_zoom["distance"] + 0.1
            assert actual_distance_from_target >= required_radial_distance - 0.001
            record(
                "exterior-minimum-clearance",
                actual_distance_from_target_m=actual_distance_from_target,
                required_radial_distance_m=required_radial_distance,
                scope="Radial exit from camera-sphere-expanded mesh bounds; not triangle distance",
            )
            await capture("exterior-minimum-zoom")
            await _key(client, "R")

            for index, lighting in ((1, "daylight"), (2, "night"), (0, "studio")):
                await _click(client, "showroom.lighting")
                popup = await _state(
                    client, lambda value: value["lighting_popup_open"],
                    "Lighting popup did not open",
                )
                for _ in range(3):
                    if popup["lighting_popup_index"] == index:
                        break
                    next_index = (popup["lighting_popup_index"] + 1) % 3
                    await _key(client, "Down")
                    popup = await _state(
                        client, lambda value, expected=next_index:
                        value["lighting_popup_index"] == expected,
                        "Actual lighting popup focus did not move one row",
                    )
                assert popup["lighting_popup_index"] == index
                await _key(client, "Enter")
                selected = await _state(
                    client, lambda value, expected=lighting: value["lighting"] == expected
                    and not value["lighting_popup_open"],
                    f"The actual lighting popup did not select {lighting}",
                )
                record("lighting-" + lighting, viewer=selected)
                measured = await _measured_case(client, "overview:" + lighting)
                record("metrics-lighting-" + lighting, viewer=measured)
                await capture("lighting-" + lighting)

            for control in ("headlights", "wipers", "hazards"):
                before = (await client.describe(ROOT))["test_state"][control]
                await _click(client, "showroom." + control)
                enabled = await _state(
                    client, lambda value, name=control, prior=before: value[name] is not prior,
                    f"The actual {control} presentation did not toggle",
                )
                record(control + "-toggled", viewer=enabled)
                await _click(client, "showroom." + control)
                await _state(
                    client, lambda value, name=control, prior=before: value[name] is prior,
                    f"The actual {control} presentation did not return to its previous state",
                )
            await _click(client, "showroom.close-all")
            await _state(
                client, lambda value: _openings_match(value, set()), "Photo hinges did not close",
            )
            await _click(client, "showroom.photo")
            photographed = await _state(
                client, lambda value: bool(value["photo_path"]), "Photo was not saved",
            )
            photo_path = Path(photographed["photo_path"]).resolve()
            assert photo_path.is_relative_to(user_data / "showroom/photos")
            photo_bytes = photo_path.read_bytes()
            photo_copy = artifacts / "showroom-photo-output.png"
            photo_copy.write_bytes(photo_bytes)
            with Image.open(photo_copy) as photo:
                assert photo.format == "PNG" and photo.width >= 960 and photo.height >= 540
                photo.load()
                dimensions = photo.size
                assert dimensions == (
                    photographed["viewport_width"], photographed["viewport_height"],
                )
                assert any(low != high for low, high in photo.convert("RGB").getextrema())
            record("photo", source_path=str(photo_path), retained_path=str(photo_copy),
                   bytes=len(photo_bytes), sha256=hashlib.sha256(photo_bytes).hexdigest(),
                   dimensions=dimensions, viewer=photographed)
            focus_sequence = await _controller_focus(client, "showroom.hide-ui")
            record("controller-focus-hide", focus_sequence=focus_sequence)
            await _joy_button(client, "a")
            hidden = await _state(
                client, lambda value: not value["ui_visible"], "Hide controls did not hide UI",
            )
            assert not (await client.describe("showroom.view.overview"))["visible"]
            record("hidden-ui", viewer=hidden)
            await capture("hidden-ui")
            await _joy_button(client, "right_stick")
            restored = await _state(
                client, lambda value: value["ui_visible"], "R3 did not restore controls",
            )
            focus_sequence = await _controller_focus(client, "showroom.photo")
            record("controller-focus-after-restore", viewer=restored, focus_sequence=focus_sequence)
            previous_photo = restored["photo_path"]
            await _joy_button(client, "a")
            controller_photo = await _state(
                client, lambda value: bool(value["photo_path"])
                and value["photo_path"] != previous_photo,
                "Controller activation after restoring UI did not save another actual photo",
            )
            controller_photo_path = Path(controller_photo["photo_path"]).resolve()
            assert controller_photo_path.is_relative_to(user_data / "showroom/photos")
            controller_bytes = controller_photo_path.read_bytes()
            retained_controller_photo = artifacts / "showroom-controller-photo-output.png"
            retained_controller_photo.write_bytes(controller_bytes)
            record("controller-photo-after-restore", viewer=controller_photo,
                   path=str(retained_controller_photo), bytes=len(controller_bytes),
                   sha256=hashlib.sha256(controller_bytes).hexdigest())
            await _key(client, "F1")
            await _state(client, lambda value: not value["ui_visible"], "F1 did not hide controls")
            await _key(client, "F1")
            await _state(client, lambda value: value["ui_visible"], "F1 did not restore controls")

            # The display copy is deliberately discarded on return. Only the
            # unchanged driving actor and original inspection panel may remain.
            await _click(client, "showroom.close")
            returned = await wait_for_describe(
                client, PANEL,
                lambda value: value["test_state"]["open"] and value["test_state"]["body_frozen"],
                "Showroom close did not restore the original parked inspection panel", timeout=10,
            )
            after = await wait_for_describe(
                client, "run.session",
                lambda value: value["test_state"]["clock_ticks_msec"] > parked["clock_ticks_msec"],
                "Main did not refresh its actual run state at the return boundary", timeout=10,
            )
            after_run = after["test_state"]
            record("returned", panel=returned["test_state"], before=parked, after=after_run)
            presentation_keys = (
                "headlamp_mode", "wipers", "hazards", "indicator_direction",
                *("opening_" + name for name in OPENINGS),
                *("angle_" + name for name in OPENINGS),
            )
            assert {key: returned["test_state"][key] for key in presentation_keys} == {
                key: original_panel["test_state"][key] for key in presentation_keys
            }, "Private viewer controls changed the hidden driving vehicle's presentation"
            assert {key: after_run[key] for key in PARKED_RUN_FIELDS} == {
                key: parked[key] for key in PARKED_RUN_FIELDS
            }, "The modal changed the parked driving actor or authoritative run state"
            assert after_run["elapsed_seconds"] == pytest.approx(
                parked["elapsed_seconds"], rel=0, abs=0.01,
            ), "Showroom wall time leaked into the paused run clock"
            assert not (await client.describe("menu.driver.root"))["visible"]
            focused = await client.request("ui.focused")
            assert focused["automation_id"] == "vehicle.inspection.close"

            await _click(client, "vehicle.inspection.showroom")
            reopened = await _state(
                client, lambda value: value["view"] == "overview" and value["rendered_frames"] > 0,
                "Showroom did not reopen",
            )
            assert reopened["vehicle_instance_id"] != opened["vehicle_instance_id"]
            assert reopened["world_instance_id"] != opened["world_instance_id"]
            record("reopened", viewer=reopened)
            await client.request("input.key", {"key": "W", "state": "press"})
            try:
                await _key(client, "Escape")
                await wait_for_describe(
                    client, PANEL, lambda value: value["test_state"]["open"],
                    "Escape did not return to the original inspection panel", timeout=10,
                )
                await _key(client, "F2")
                await wait_for_describe(
                    client, PANEL, lambda value: not value["test_state"]["open"],
                    "The original F2 close path did not resume driving", timeout=10,
                )
                suppressed = await wait_for_conditioner(
                    client, lambda value: value["conditioned_throttle"] == 0
                    and value["last_suppression_reason"] == "vehicle_inspection_closed",
                    "A driving key held in the modal leaked through the original inspection close",
                    timeout=10,
                )
                record("held-input-return", conditioner=suppressed)
            finally:
                await client.request("input.key", {"key": "W", "state": "release"})
            await capture("returned-driving")
    except BaseException as error:
        record("failed", error_type=type(error).__name__, message=str(error))
        raise
    finally:
        _write_observations(observation_path, observations)
        if process.teardown_result is not None:
            (artifacts / "showroom-teardown.json").write_text(
                json.dumps(process.teardown_result, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
    assert isolated is not None and not isolated.exists()
    (artifacts / "showroom-summary.json").write_text(json.dumps({
        "status": "passed", "scope": "actual rendered viewer input and modal restoration",
        "rendering_method": rendering_method, "renderer_observed": opened["renderer"],
        "window_size_requested": window_size,
        "viewport_size_observed": [opened["viewport_width"], opened["viewport_height"]],
        "vehicle": "endurance-sedan",
        "camera_presets": list(VIEWS), "independent_openings": list(OPENINGS),
        "observations": observations, "images": images,
        "teardown": process.teardown_result, "human_approval": None,
        "metrics_scope": "Short frame intervals; no GPU duration or reference-PC performance pass",
        "metrics_statistics_refresh_seconds": 1,
    }, indent=2, allow_nan=False) + "\n", encoding="utf-8")
