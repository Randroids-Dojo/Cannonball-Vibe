from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
from pathlib import Path

import pytest

from cannonball_playgodot import PlayGodotClient, PlayGodotProcess

from .input_support import wait_for_conditioner, wait_for_describe

REPO_ROOT = Path(__file__).resolve().parents[3]
PANEL = "vehicle.inspection.panel"
WINDOW = "vehicle.inspection.window"
OPENINGS = {
    "Door_FL": 62, "Door_FR": 62, "Door_RL": 58, "Door_RR": 58,
    "Hood_Hinge": 68, "Trunk_Hinge": 72,
}


async def _key(client: PlayGodotClient, key: str) -> None:
    for state in ("press", "release"):
        await client.request("input.key", {"key": key, "state": state})


async def _button(client: PlayGodotClient, button: str) -> None:
    for state in ("press", "release"):
        await client.request(
            "input.joypad_button", {"button": button, "state": state, "device": 0},
        )


async def _state(client: PlayGodotClient, **expected: object) -> dict:
    try:
        description = await wait_for_describe(
            client, PANEL,
            lambda value: all(
                value["test_state"].get(key) == item for key, item in expected.items()
            ),
            f"Vehicle panel state did not match {expected}", timeout=10,
        )
    except BaseException:
        if configured := os.environ.get("PLAYGODOT_ARTIFACT_DIR"):
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(
                    client.screenshot(Path(configured) / "sedan-inspection-failure.png"), 5,
                )
        raise
    return description["test_state"]


async def _click(client: PlayGodotClient, automation_id: str) -> None:
    control, window = await client.describe(automation_id), await client.describe(WINDOW)
    assert control["visible"] and control["enabled"]
    bounds, panel = control["bounds"], window["bounds"]
    center = (bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
    assert panel["x"] <= center[0] <= panel["x"] + panel["width"]
    assert panel["y"] <= center[1] <= panel["y"] + panel["height"]
    await client.request("input.click", {"automation_id": automation_id})


async def _clock_after(client: PlayGodotClient, ticks: int) -> dict:
    description = await wait_for_describe(
        client, "run.session", lambda value: value["test_state"]["clock_ticks_msec"] >= ticks,
        "The actual engine clock did not reach the observation time", timeout=10,
    )
    return description["test_state"]


async def _pause_trip_map(client: PlayGodotClient, observations: list[dict]) -> None:
    await _key(client, "M")
    await wait_for_describe(
        client, "trip-map.root", lambda value: value["test_state"]["open"]
        and value["test_state"]["simulation_paused"],
        "The actual trip map did not pause the simulation", timeout=10,
    )
    before = await _clock_after(client, 0)
    after = await _clock_after(client, before["clock_ticks_msec"] + 3500)
    assert after["elapsed_seconds"] == pytest.approx(before["elapsed_seconds"], abs=0.01)
    observations.append({"stage": "trip-map-pause", "before": before, "after": after})
    await _key(client, "Escape")
    await wait_for_describe(
        client, "trip-map.root", lambda value: not value["test_state"]["open"],
        "The trip map did not return to driving", timeout=10,
    )


async def _verify_selected_clock_and_save(
    client: PlayGodotClient, selection: str, user_data: Path, observations: list[dict],
    artifacts: Path, prior: dict,
) -> None:
    selected = await wait_for_describe(
        client, "run.session", lambda value: value["test_state"]["selected_asset"] == selection,
        "The run clock did not report the reconstructed vehicle", timeout=10,
    )
    before = selected["test_state"]
    assert before["elapsed_seconds"] >= prior["elapsed_seconds"], "Selection reset carried run time"
    horizontal_error = sum(
        (before["vehicle_position_" + axis] - prior["vehicle_position_" + axis]) ** 2
        for axis in ("x", "z")
    ) ** 0.5
    observations.append({"stage": "stationary-selection-" + selection,
                         "before": prior, "after": before,
                         "observed_horizontal_error_m": horizontal_error})
    # UI readback follows the new body's first physics ticks. The separate
    # boundary witness checks exact reconstruction; this bounds later drift
    # and rejects the old 20 m lookahead teleport through the real UI.
    (artifacts / "sedan-selection-clock-observations.json").write_text(
        json.dumps(observations, indent=2) + "\n",
    )
    assert horizontal_error <= 0.25, "Parked selection moved to the road lookahead target"
    after = await _clock_after(client, before["clock_ticks_msec"] + 1000)
    wall_seconds = (after["clock_ticks_msec"] - before["clock_ticks_msec"]) / 1000
    elapsed_seconds = after["elapsed_seconds"] - before["elapsed_seconds"]
    observations.append({"stage": "clock-after-" + selection, "before": before, "after": after,
                         "observed_wall_seconds": wall_seconds,
                         "observed_elapsed_seconds": elapsed_seconds})
    # Retain the actual before/after values even when the regression rejects a
    # candidate before the final completion artifact can be written.
    (artifacts / "sedan-selection-clock-observations.json").write_text(
        json.dumps(observations, indent=2) + "\n",
    )
    assert elapsed_seconds == pytest.approx(wall_seconds, abs=0.01), (
        "Selection deducted an already-accounted map pause from the new run-clock interval"
    )
    await _key(client, "F5")
    save_path = user_data / "runs/suspended-run.json"
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        if save_path.is_file():
            saved_bytes = save_path.read_bytes()
            saved = json.loads(saved_bytes)
            if saved["run"]["elapsedSeconds"] >= after["elapsed_seconds"]:
                break
        assert asyncio.get_running_loop().time() < deadline, (
            "F5 did not persist the current run clock"
        )
        await asyncio.sleep(0.05)
    # The bridge exposes Main's cached process sample. Reading the completed
    # save does not make that sample newer than the later-in-frame F5 capture.
    # Observe the cache after the file read, then require a newer sample. The
    # saved value never participates in this readiness predicate.
    save_read_barrier = (await client.describe("run.session"))["test_state"]
    assert save_read_barrier["clock_ticks_msec"] >= after["clock_ticks_msec"]
    following = await _clock_after(client, save_read_barrier["clock_ticks_msec"] + 1)
    (artifacts / f"sedan-selection-{selection}-save.json").write_bytes(saved_bytes)
    observations.append({"stage": "save-clock-" + selection,
                         "saved_elapsed_seconds": saved["run"]["elapsedSeconds"],
                         "save_read_barrier": save_read_barrier,
                         "following": following,
                         "following_elapsed_seconds": following["elapsed_seconds"],
                         "save_sha256": hashlib.sha256(saved_bytes).hexdigest()})
    (artifacts / "sedan-selection-clock-observations.json").write_text(
        json.dumps(observations, indent=2) + "\n",
    )
    assert saved["run"]["elapsedSeconds"] <= following["elapsed_seconds"] + 0.01


@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="GODOT_BIN enables live 4.7.1 tests")
@pytest.mark.asyncio
async def test_endurance_sedan_inspection_and_selection_controls(tmp_path: Path) -> None:
    """Exercise the actual parked Control surface; native art/feel QA stays separate."""
    package_root = REPO_ROOT / ".tools/scenarios/official-corridor"
    pointer = json.loads((package_root / "current-package.json").read_text())
    artifacts = Path(os.environ.get("PLAYGODOT_ARTIFACT_DIR", str(tmp_path)))
    artifacts.mkdir(parents=True, exist_ok=True)
    process = PlayGodotProcess(
        REPO_ROOT, package_root / pointer["root_relative_path"],
        vehicle="endurance-sedan", isolate_user_data=True,
        capabilities=("read", "input", "screenshot"), startup_timeout=60, request_timeout=30,
        transcript=artifacts / "sedan-inspection.jsonl",
        log_path=artifacts / "sedan-inspection-godot.log",
    )
    observations: list[dict] = []
    async with asyncio.timeout(240), process as client:
        initial = await _state(client, selected_asset="endurance-sedan", open=False)
        assert process._runtime_directory is not None
        isolated = process._runtime_directory.resolve()
        user_data = Path(initial["user_data_directory"]).resolve()
        assert user_data.is_relative_to(isolated), "Selection must not write real player settings"
        assert not (user_data / "vehicle-presentation.cfg").exists()
        await wait_for_describe(
            client, "run.session", lambda value: value["test_state"]["linear_speed_mps"] <= 0.5,
            "Vehicle did not settle within the existing parked inspection threshold", timeout=10,
        )
        await _key(client, "F2")
        opened = await _state(client, selected_asset="endurance-sedan", open=True, body_frozen=True)
        assert (await client.describe(WINDOW))["visible"]
        assert (await client.request("ui.focused"))["automation_id"] == "vehicle.inspection.close"
        assert "Meridian S8R" in (await client.describe("vehicle.inspection.status"))["text"]
        observations.append({"stage": "keyboard-open", "state": opened})
        image = await client.screenshot(artifacts / "sedan-inspection-keyboard.png")
        assert image["bytes"] > 0 and image["width"] >= 960 and image["height"] >= 540

        for control, expected in (
            ("headlights", {"headlamp_mode": 1}), ("wipers", {"wipers": True}),
            ("signal-left", {"indicator_direction": -1}),
            ("signal-right", {"indicator_direction": 1}), ("hazards", {"hazards": True}),
        ):
            await _click(client, "vehicle.controls." + control)
            observations.append({"stage": control, "state": await _state(client, **expected)})
        status = (await client.describe("vehicle.inspection.status"))["text"]
        assert "Headlights: On" in status and "Wipers: On" in status and "Hazards: On" in status
        initial_camera = opened["camera_mode"]
        await _click(client, "vehicle.controls.camera")
        camera = await wait_for_describe(
            client, PANEL, lambda value: value["test_state"]["camera_mode"] != initial_camera,
            "Inspection camera button did not switch the actual camera", timeout=10,
        )
        observations.append({"stage": "camera-switch", "state": camera["test_state"]})
        await _click(client, "vehicle.controls.camera")
        await _state(client, camera_mode=initial_camera)

        for name in OPENINGS:
            await _click(client, "vehicle.opening." + name.lower().replace("_", "-"))
        all_open = await wait_for_describe(
            client, PANEL,
            lambda value: all(
                value["test_state"]["opening_" + name]
                and abs(value["test_state"]["angle_" + name]) >= angle * 0.95
                for name, angle in OPENINGS.items()
            ), "Six UI opening buttons did not produce their actual joint motion", timeout=10,
        )
        observations.append({"stage": "six-openings", "state": all_open["test_state"]})
        await client.screenshot(artifacts / "sedan-inspection-openings.png")
        for name in OPENINGS:
            await _click(client, "vehicle.opening." + name.lower().replace("_", "-"))
        await wait_for_describe(
            client, PANEL,
            lambda value: all(
                not value["test_state"]["opening_" + name]
                and abs(value["test_state"]["angle_" + name]) <= 0.1 for name in OPENINGS
            ), "Six UI openings did not close", timeout=10,
        )
        await _key(client, "Escape")
        await _state(client, open=False, body_frozen=initial["body_frozen"])
        assert not (await client.describe(WINDOW))["visible"]
        assert not (await client.describe("menu.driver.root"))["visible"]
        await client.screenshot(artifacts / "sedan-inspection-escape.png")

        await _button(client, "right_shoulder")
        await _state(client, open=True, body_frozen=True)
        await _button(client, "dpad_up")
        assert (await client.request("ui.focused"))["automation_id"] == "vehicle.selection.apply"
        await _button(client, "dpad_down")
        assert (await client.request("ui.focused"))["automation_id"] == "vehicle.inspection.close"
        await client.screenshot(artifacts / "sedan-inspection-controller.png", automation_id=WINDOW)
        await _button(client, "b")
        await _state(client, open=False, body_frozen=initial["body_frozen"])

        await _pause_trip_map(client, observations)
        for selection, index, label in (("hero-gt", 1, "Hero GT"), ("graybox", 2, "Graybox"),
                                         ("endurance-sedan", 0, "Meridian S8R")):
            await wait_for_describe(
                client, "run.session", lambda value: value["test_state"]["linear_speed_mps"] <= 0.5
                and value["test_state"]["grounded_wheel_count"] == 4,
                "Selected vehicle did not settle to the existing parked guard", timeout=10,
            )
            await _key(client, "F2")
            await _state(client, open=True, body_frozen=True)
            await _click(client, "vehicle.selection.options")
            popup = await _state(client, selection_popup_open=True)
            # PopupMenu supports up/down navigation; it does not bind Home.
            # Start from its actual focused row, including -1 after a mouse click.
            for _ in range(3):
                if popup["selection_popup_index"] == index:
                    break
                expected_index = (popup["selection_popup_index"] + 1) % 3
                await _key(client, "Down")
                popup = await _state(client, selection_popup_index=expected_index)
            assert popup["selection_popup_index"] == index
            await _key(client, "Enter")
            await _state(client, selection_popup_open=False)
            await wait_for_describe(
                client, "vehicle.selection.options",
                lambda value, expected_label=label: expected_label in value["text"],
                f"Actual option popup did not select {selection}", timeout=10,
            )
            before_selection = await _clock_after(client, 0)
            previous_render_generation = process.rendered_vehicle_generation
            await _click(client, "vehicle.selection.apply")
            rendered = await process.wait_for_vehicle_render(
                selection, after_generation=previous_render_generation, timeout=60,
            )
            observations.append({"stage": "render-ready-" + selection, "render": rendered})
            selected = await _state(client, selected_asset=selection, open=False)
            assert Path(selected["user_data_directory"]).resolve() == user_data
            settings = (user_data / "vehicle-presentation.cfg").read_text()
            assert f'asset_id="{selection}"' in settings
            observations.append({"stage": "select-" + selection, "state": selected})
            await _verify_selected_clock_and_save(
                client, selection, user_data, observations, artifacts,
                before_selection,
            )

        await wait_for_describe(
            client, "run.session", lambda value: value["test_state"]["linear_speed_mps"] <= 0.5
            and value["test_state"]["grounded_wheel_count"] == 4,
            "Restored sedan did not settle to the existing parked guard", timeout=10,
        )
        await _key(client, "F2")
        await _state(client, open=True)
        await client.request("input.key", {"key": "W", "state": "press"})
        try:
            await _key(client, "F2")
            await _state(client, open=False, body_frozen=initial["body_frozen"])
            cleared = await wait_for_conditioner(
                client, lambda value: value["conditioned_throttle"] == 0
                and value["last_suppression_reason"] == "vehicle_inspection_closed",
                "Closing inspection did not clear latched driving input", timeout=10,
            )
            observations.append({"stage": "held-input-close", "state": cleared})
        finally:
            await client.request("input.key", {"key": "W", "state": "release"})
        settings_bytes = (user_data / "vehicle-presentation.cfg").read_bytes()
        (artifacts / "sedan-inspection-settings.cfg").write_bytes(settings_bytes)
        (artifacts / "sedan-inspection-summary.json").write_text(json.dumps({
            "status": "passed", "scope": "rendered Control input/selection; not native art/feel QA",
            "isolated_user_data": str(user_data), "observations": observations,
            "settings_sha256": hashlib.sha256(settings_bytes).hexdigest(), "human_approval": None,
        }, indent=2) + "\n")
    assert not isolated.exists(), "The disposable profile must be removed after the test"
