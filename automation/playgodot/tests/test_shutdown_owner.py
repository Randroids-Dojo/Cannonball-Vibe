from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from cannonball_playgodot import PlayGodotProcess
from cannonball_playgodot.launcher import ShutdownError

from .shutdown_support import assert_clean_owned_shutdown

ROOT = Path(__file__).resolve().parents[3]
BRIDGE = ROOT / "addons/playgodot/server.gd"
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        "GODOT_BIN" not in os.environ,
        reason="GODOT_BIN enables live official-engine tests",
    ),
]


def _artifacts(tmp_path: Path, name: str) -> Path:
    base = Path(os.environ.get("PLAYGODOT_ARTIFACT_DIR", str(tmp_path)))
    out = base / f"shutdown-owner-{name}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _route_package() -> Path:
    base = ROOT / ".tools/scenarios/official-corridor"
    return base / json.loads((base / "current-package.json").read_text())["root_relative_path"]


def _result(process: PlayGodotProcess, out: Path) -> dict:
    result = process.teardown_result
    (out / "owner-result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result is not None
    return result


def _assert_clean(process: PlayGodotProcess, out: Path) -> str:
    result = _result(process, out)
    assert_clean_owned_shutdown(result)
    return (out / "godot.log").read_text()


def _simple_project(
    tmp_path: Path, owner_path: str, *, change: str = "", handles: bool = True
) -> Path:
    project = tmp_path / "fixture"
    addon = project / "addons/playgodot"
    addon.mkdir(parents=True)
    shutil.copyfile(BRIDGE, addon / "server.gd")
    (project / "project.godot").write_text("""config_version=5
[application]
config/name="Owned shutdown fixture"
run/main_scene="res://addons/playgodot/bootstrap.tscn"
[rendering]
renderer/rendering_method="gl_compatibility"
""")
    (project / "owner.gd").write_text(
        """extends Node
func _notification(what: int) -> void:
    if what == NOTIFICATION_WM_CLOSE_REQUEST:
        print("TEST_OWNER_NOTIFICATION")
"""
        + ("        get_tree().quit(0)\n" if handles else "        pass\n")
    )
    (project / "fixture.gd").write_text(
        """extends Node
func _ready() -> void:
    $Change.pressed.connect(_change)
func _change() -> void:
"""
        + {
            "": "    pass\n",
            "free": "    $Owner.free()\n",
            "replace": (
                '    $Owner.free()\n    var replacement := Node.new()\n'
                '    replacement.name = "Owner"\n    add_child(replacement)\n'
            ),
            "detach": "    var prior := $Owner\n    remove_child(prior)\n    prior.queue_free()\n",
            "clear": '    $Bridge.application_quit_owner = NodePath("")\n',
        }[change]
    )
    (addon / "bootstrap.tscn").write_text(
        """[gd_scene load_steps=4 format=3]
[ext_resource type="Script" path="res://addons/playgodot/server.gd" id="1"]
[ext_resource type="Script" path="res://owner.gd" id="2"]
[ext_resource type="Script" path="res://fixture.gd" id="3"]
[node name="Fixture" type="Node"]
script = ExtResource("3")
[node name="Bridge" type="Node" parent="."]
script = ExtResource("1")
application_quit_owner = NodePath("""
        + json.dumps(owner_path)
        + """)
[node name="Owner" type="Node" parent="."]
script = ExtResource("2")
[node name="Change" type="Button" parent="."]
offset_right = 200.0
offset_bottom = 80.0
text = "Change owner"
metadata/automation_id = "fixture.change-owner"
"""
    )
    return project


@pytest.mark.parametrize("owner_path", ["", "../Owner"])
async def test_generic_bridge_direct_and_declared_owner(tmp_path: Path, owner_path: str) -> None:
    out = _artifacts(tmp_path, "direct" if not owner_path else "declared")
    process = PlayGodotProcess(
        _simple_project(out, owner_path),
        _route_package(),
        log_path=out / "godot.log",
        transcript=out / "wire.jsonl",
        isolate_user_data=True,
    )
    async with process as client:
        assert await client.request("session.ping") == {"ok": True}
    log = _assert_clean(process, out)
    assert ("TEST_OWNER_NOTIFICATION" in log) == bool(owner_path)
    modes = [
        json.loads(line.split(" ", 1)[1])["mode"]
        for line in log.splitlines()
        if line.startswith("PLAYGODOT_QUIT_OWNER ")
    ]
    assert modes == ["application" if owner_path else "direct"]


@pytest.mark.parametrize(
    "owner_path", ["../Missing", ".", "/root/Fixture/Owner", "../Owner:script"]
)
async def test_invalid_configured_owner_fails_before_accepting_requests(
    tmp_path: Path,
    owner_path: str,
) -> None:
    label = {
        "../Missing": "missing",
        ".": "self",
        "/root/Fixture/Owner": "absolute",
        "../Owner:script": "property",
    }[owner_path]
    out = _artifacts(tmp_path, label)
    process = PlayGodotProcess(
        _simple_project(out, owner_path),
        _route_package(),
        log_path=out / "godot.log",
        isolate_user_data=True,
    )
    with pytest.raises(RuntimeError, match="Godot exited before PlayGodot was ready"):
        await process.start()
    log = (out / "godot.log").read_text()
    result = _result(process, out)
    assert result["exit_status"] == 1 and result["status"] == "failed"
    assert "PLAYGODOT_START_FAILED" in log
    assert "PLAYGODOT_READY " not in log and "TEST_OWNER_NOTIFICATION" not in log


@pytest.mark.parametrize("change", ["free", "replace", "detach", "clear"])
async def test_stale_owner_does_not_fall_back_to_success(tmp_path: Path, change: str) -> None:
    out = _artifacts(tmp_path, change)
    process = PlayGodotProcess(
        _simple_project(out, "../Owner", change=change),
        _route_package(),
        capabilities=("read", "input"),
        log_path=out / "godot.log",
        isolate_user_data=True,
    )
    with pytest.raises(ShutdownError):
        async with process as client:
            await client.request("input.click", {"automation_id": "fixture.change-owner"})
            await client.request("session.ping")
    result = _result(process, out)
    assert result["status"] == "failed" and result["exit_status"] == 1
    assert result["fallback"] == []
    assert "PLAYGODOT_QUIT_OWNER_FAILED" in (out / "godot.log").read_text()


async def test_nonhandling_owner_cannot_claim_success(tmp_path: Path) -> None:
    out = _artifacts(tmp_path, "nonhandling")
    process = PlayGodotProcess(
        _simple_project(out, "../Owner", handles=False),
        _route_package(),
        log_path=out / "godot.log",
        isolate_user_data=True,
    )
    with pytest.raises(ShutdownError):
        async with process as client:
            await client.request("session.ping")
    result = _result(process, out)
    assert result["status"] == "failed" and result["fallback"]
    assert result["total_budget_seconds"] == 8.0
    assert "TEST_OWNER_NOTIFICATION" in (out / "godot.log").read_text()


async def _wait(client, target: str, predicate, reason: str) -> dict:
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        value = await client.describe(target)
        if predicate(value):
            return value
        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail(f"{reason}: {value}")
        await asyncio.sleep(0.02)


@pytest.mark.parametrize("scene_kind", ["main", "embedded", "standalone"])
async def test_existing_application_owner_drains_managed_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scene_kind: str,
) -> None:
    out = _artifacts(tmp_path, scene_kind)
    generated = (
        out / "fixture"
        if out.is_relative_to(ROOT)
        else ROOT / "reports/playgodot/owner-fixtures" / uuid.uuid4().hex
    )
    generated.mkdir(parents=True)
    shutil.copyfile(BRIDGE, generated / "server.gd")
    bridge_uri = "res://" + (generated / "server.gd").relative_to(ROOT).as_posix()
    scene = generated / "fixture.tscn"
    if scene_kind == "standalone":
        scene.write_text(
            '''[gd_scene load_steps=3 format=3]
[ext_resource type="Script" path="'''
            + bridge_uri
            + """" id="1"]
[ext_resource type="PackedScene" path="res://game/Vehicle/Showroom/VehicleShowroom.tscn" id="2"]
[node name="StandaloneFixture" type="Node"]
[node name="Bridge" type="Node" parent="."]
script = ExtResource("1")
application_quit_owner = NodePath("../VehicleShowroom")
[node name="VehicleShowroom" parent="." instance=ExtResource("2")]
"""
        )
    else:
        source = (ROOT / "addons/playgodot/bootstrap.tscn").read_text()
        source = source.replace("res://addons/playgodot/server.gd", bridge_uri)
        if "application_quit_owner" not in source:
            source = source.replace(
                'script = ExtResource("2_server")',
                'script = ExtResource("2_server")\napplication_quit_owner = NodePath("../Main")',
            )
        scene.write_text(source)
    actual_spawn = asyncio.create_subprocess_exec
    commands = []

    async def spawn(*args, **kwargs):
        command = list(args)
        assert command.count("addons/playgodot/bootstrap.tscn") == 1
        command[command.index("addons/playgodot/bootstrap.tscn")] = scene.relative_to(
            ROOT
        ).as_posix()
        if scene_kind == "main":
            command.append("--managed-shutdown-probe")
        commands.append(command)
        return await actual_spawn(*command, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    process = PlayGodotProcess(
        ROOT,
        _route_package(),
        vehicle="endurance-sedan" if scene_kind != "main" else "graybox",
        startup_timeout=60, request_timeout=30,
        capabilities=("read", "input"),
        isolate_user_data=True,
        log_path=out / "godot.log",
        transcript=out / "wire.jsonl",
    )
    try:
        async with process as client:
            if scene_kind == "embedded":
                await _wait(
                    client,
                    "run.session",
                    lambda d: (
                        d["test_state"]["linear_speed_mps"] <= 0.5
                        and d["test_state"]["grounded_wheel_count"] == 4
                    ),
                    "Sedan did not park",
                )
                for state in ("press", "release"):
                    await client.request("input.key", {"key": "F2", "state": state})
                await _wait(
                    client,
                    "vehicle.inspection.panel",
                    lambda d: d["test_state"]["open"],
                    "Inspection did not open",
                )
                await client.request(
                    "input.click", {"automation_id": "vehicle.inspection.showroom"}
                )
            if scene_kind != "main":
                viewer = await _wait(
                    client,
                    "showroom.root",
                    lambda d: d["test_state"]["rendered_frames"] > 0,
                    "Showroom did not render",
                )
                state = viewer["test_state"]
                assert state["asset_id"] == "endurance-sedan" and state["private_world"]
                if scene_kind == "embedded":
                    assert state["run_paused"]
                (out / "viewer-before-quit.json").write_text(json.dumps(viewer, indent=2) + "\n")
        log = _assert_clean(process, out)
        assert "CANNONBALL_SHUTDOWN_OK drains=2 producers_stopped=true" in log
        owners = [
            json.loads(line.split(" ", 1)[1])
            for line in log.splitlines()
            if line.startswith("PLAYGODOT_QUIT_OWNER ")
        ]
        assert len(owners) == 1 and owners[0]["mode"] == "application"
        assert owners[0]["path"].endswith(
            "/VehicleShowroom" if scene_kind == "standalone" else "/Main"
        )
        if scene_kind == "main":
            assert "CANNONBALL_SHUTDOWN_PROBE_QUEUED wrappers=32 inaccessible=32" in log
            assert "CANNONBALL_SHUTDOWN_PROBE_OK wrappers=32 finalized=32" in log
    finally:
        _result(process, out)
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
