from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest
from PIL import Image

from cannonball_playgodot import PlayGodotProcess

from .shutdown_support import assert_clean_owned_shutdown

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_CASES = {
    "actual-sedan-private-world", "relative-left-orbit", "release-stops-orbit",
    "pan-2", "pan-3", "wheel-zooms-exterior", "wheel-reverses-exterior",
    "exterior-zoom-limit-4", "exterior-zoom-limit-5", "ui-does-not-start-orbit",
    "release-over-ui-stops-drag", "focus-loss-clears-drag", "wheel-zooms-cockpit-fov",
    "cockpit-drag-direction", "cockpit-does-not-pan-through-cabin",
    "cockpit-fov-limit-4", "cockpit-fov-limit-5", "live-resize-render-viewport",
    "orbit-after-resize", "restore-window", "hide-controls-after-pointer",
    "same-frozen-display-survives", "capture-01-before", "capture-02-orbit",
    "capture-03-cockpit", "capture-04-resized", "capture-05-controls-hidden",
}


@pytest.mark.asyncio
@pytest.mark.skipif("GODOT_BIN" not in os.environ, reason="Requires the official rendered engine")
async def test_showroom_native_pointer_focus_and_resize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = Path(os.environ.get("PLAYGODOT_ARTIFACT_DIR", str(tmp_path))) / "showroom-pointer"
    out.mkdir(parents=True, exist_ok=True)
    generated = (
        out / "fixture" if out.is_relative_to(ROOT)
        else ROOT / "reports/playgodot/pointer-fixtures" / uuid.uuid4().hex
    )
    generated.mkdir(parents=True)
    native_out = out if out.is_relative_to(ROOT) else generated / "native"
    native_out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CANNONBALL_SHOWROOM_POINTER_REPORT", native_out.as_posix())
    scene = generated / "fixture.tscn"
    scene.write_text('''[gd_scene load_steps=4 format=3]
[ext_resource type="Script" path="res://addons/playgodot/server.gd" id="1"]
[ext_resource type="PackedScene" path="res://game/Vehicle/Showroom/VehicleShowroom.tscn" id="2"]
[ext_resource type="Script" path="res://automation/playgodot/fixtures/showroom_pointer.gd" id="3"]
[node name="PointerFixture" type="Node"]
[node name="Bridge" type="Node" parent="."]
script = ExtResource("1")
application_quit_owner = NodePath("../VehicleShowroom")
[node name="VehicleShowroom" parent="." instance=ExtResource("2")]
[node name="PointerProbe" type="Node" parent="."]
script = ExtResource("3")
''', encoding="utf-8", newline="\n")
    commands = []
    actual_spawn = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        command = list(args)
        if "addons/playgodot/bootstrap.tscn" in command:
            command[command.index("addons/playgodot/bootstrap.tscn")] = (
                scene.relative_to(ROOT).as_posix()
            )
        commands.append(command)
        return await actual_spawn(*command, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    base = ROOT / ".tools/scenarios/official-corridor"
    package = base / json.loads((base / "current-package.json").read_bytes())["root_relative_path"]
    process = PlayGodotProcess(
        ROOT, package, vehicle="endurance-sedan", capabilities=("read", "input"),
        startup_timeout=60, request_timeout=30,
        rendering_method=os.environ.get("SHOWROOM_POINTER_RENDERER", "gl_compatibility"),
        window_size=tuple(map(int, os.environ.get(
            "SHOWROOM_POINTER_RESOLUTION", "1280x720").split("x"))), isolate_user_data=True,
        log_path=out / "godot.log", transcript=out / "wire.jsonl",
    )
    paths = [ROOT / "automation/playgodot/fixtures/showroom_pointer.gd",
             Path(__file__), ROOT / "automation/playgodot/tests/shutdown_support.py",
             ROOT / "game/Vehicle/Showroom/VehicleShowroom.cs",
             ROOT / "game/Vehicle/Showroom/ShowroomInterface.cs",
             ROOT / "game/Vehicle/Showroom/ShowroomStudio.cs",
             ROOT / ".godot/mono/temp/bin/Debug/Cannonball.dll",
             ROOT / ".godot/mono/temp/bin/Debug/Cannonball.Core.dll",
             ROOT / "data/assets/vehicles/derived/endurance-sedan.glb",
             ROOT / "addons/playgodot/server.gd", scene]
    inputs = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths}
    try:
        async with process as client:
            await client.request("input.click", {"automation_id": "showroom.pointer-probe.start"})
            deadline = asyncio.get_running_loop().time() + 180
            while True:
                result = (await client.describe("showroom.pointer-probe"))["test_state"]
                if result["status"] in {"passed", "failed"}:
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    pytest.fail(f"Native pointer probe did not complete: {result}")
                await asyncio.sleep(0.1)
            (out / "observed-state.json").write_text(json.dumps(result, indent=2) + "\n")
            result = json.loads((native_out / "native-results.json").read_bytes())
            assert result["status"] == "passed", result
            assert len(result["cases"]) == len(EXPECTED_CASES)
            assert {case["case"] for case in result["cases"]} == EXPECTED_CASES
            assert all(case["passed"] for case in result["cases"])
            assert len(result["captures"]) == 5
            if native_out != out:
                shutil.copyfile(native_out / "native-results.json", out / "native-results.json")
            for capture in result["captures"]:
                path = Path(capture["path"])
                with Image.open(path) as image:
                    assert image.size == tuple(capture["size"])
                    assert any(high - low > 10 for low, high in image.convert("RGB").getextrema())
                if native_out != out:
                    shutil.copyfile(path, out / path.name)
        shutdown = process.teardown_result
        assert_clean_owned_shutdown(shutdown)
        log = (out / "godot.log").read_text()
        assert "CANNONBALL_SHUTDOWN_OK drains=2 producers_stopped=true" in log
    finally:
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        (out / "teardown.json").write_text(json.dumps(process.teardown_result, indent=2) + "\n")
        after = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in paths}
        (out / "bindings.json").write_text(json.dumps({"before": inputs, "after": after,
                                                       "unchanged": inputs == after}, indent=2))
        assert inputs == after
