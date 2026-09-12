from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cannonball_playgodot import PlayGodotProcess
from cannonball_playgodot.client import ProtocolError


@pytest.mark.parametrize("vehicle", [None, "endurance-sedan", "hero-gt", "graybox"])
@pytest.mark.parametrize("production_vehicle", [False, True])
@pytest.mark.asyncio
async def test_explicit_vehicle_and_disposable_profile_preserve_default_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vehicle: str | None,
    production_vehicle: bool,
) -> None:
    route = tmp_path / "fixture.cbrg"
    route.write_bytes(b"fixture")
    child = SimpleNamespace(stdout=asyncio.StreamReader())
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setenv("HOME", str(tmp_path / "real-user-home"))
    process = PlayGodotProcess(
        tmp_path, route, godot_bin=Path(sys.executable), vehicle=vehicle,
        isolate_user_data=vehicle is not None, production_vehicle=production_vehicle,
    )
    monkeypatch.setattr(process, "_read_ready", AsyncMock(side_effect=RuntimeError("stop probe")))
    monkeypatch.setattr(process, "_stop_process", AsyncMock())
    with pytest.raises(RuntimeError, match="stop probe"):
        await process.start()
    command = spawn.call_args.args
    environment = spawn.call_args.kwargs["env"]
    if vehicle is None:
        intended = "hero-gt" if production_vehicle else "graybox"
        assert [arg for arg in command if arg.startswith("--vehicle=")] == [f"--vehicle={intended}"]
        assert ("--graybox-vehicle" in command) is not production_vehicle
        assert environment["HOME"] == str(tmp_path / "real-user-home")
    else:
        assert f"--vehicle={vehicle}" in command
        assert "--graybox-vehicle" not in command
        isolated = Path(environment["HOME"])
        assert isolated.name.startswith("cannonball-playgodot-")
        assert not isolated.exists(), "The launch failure must clean its disposable profile"
        for key in ("XDG_DATA_HOME", "APPDATA", "LOCALAPPDATA"):
            assert Path(environment[key]).is_relative_to(isolated)
    assert process._runtime_directory is None


def test_unknown_explicit_vehicle_is_rejected_before_launch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown explicit PlayGodot vehicle"):
        PlayGodotProcess(tmp_path, tmp_path / "fixture.cbrg", vehicle="unclaimed")


@pytest.mark.asyncio
async def test_startup_timeout_retains_engine_output_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = tmp_path / "fixture.cbrg"
    route.write_bytes(b"fixture")
    output = asyncio.StreamReader()
    output.feed_data(b"Godot starting\nrenderer initialization stalled\n")
    child = SimpleNamespace(stdout=output)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    process = PlayGodotProcess(
        tmp_path, route, godot_bin=Path(sys.executable), startup_timeout=0.01,
        log_path=tmp_path / "startup.log",
    )
    stopped = AsyncMock()
    monkeypatch.setattr(process, "stop", stopped)
    try:
        with pytest.raises(TimeoutError, match="PLAYGODOT_READY within 0.01s") as caught:
            await process.start()
        assert "renderer initialization stalled" in str(caught.value)
        assert "renderer initialization stalled" in (tmp_path / "startup.log").read_text()
        stopped.assert_awaited_once()
    finally:
        if process._runtime_directory is not None:
            process._runtime_directory.rmdir()


def _render_record(generation: int = 1, asset: str = "endurance-sedan") -> dict:
    return {
        "generation": generation, "asset_id": asset,
        "vehicle_instance_id": 100 + generation, "panel_instance_id": 200 + generation,
        "viewport_instance_id": 300, "camera_instance_id": 400 + generation,
        "pre_draw_usec": generation * 1_000, "post_draw_usec": generation * 1_000 + 20,
        "pre_process_frame": generation, "post_process_frame": generation,
        "pre_physics_frame": generation * 4, "post_physics_frame": generation * 4,
        "pre_drawn_frame": generation, "post_drawn_frame": generation,
    }


def _record_render(process: PlayGodotProcess, record: dict) -> None:
    process._record_output("PLAYGODOT_VEHICLE_RENDERED " + json.dumps(record))


@pytest.mark.asyncio
async def test_completed_vehicle_render_can_arrive_before_waiter(tmp_path: Path) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route", request_timeout=30)
    _record_render(process, _render_record())
    generation = process.rendered_vehicle_generation
    _record_render(process, _render_record(2, "hero-gt"))
    result = await process.wait_for_vehicle_render("hero-gt", after_generation=generation)
    assert result["generation"] == 2 and result["vehicle_instance_id"] == 102
    assert result["preparation_budget_seconds"] == 60
    assert result["wait_elapsed_seconds"] >= 0
    assert process.request_timeout == 30
    result["asset_id"] = "caller mutation"
    assert process._vehicle_renders[-1]["asset_id"] == "hero-gt"


@pytest.mark.asyncio
async def test_vehicle_render_waits_for_new_matching_asset_without_rpc(tmp_path: Path) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route", request_timeout=30)
    request = AsyncMock(side_effect=AssertionError("render preparation must not send an RPC"))
    process.client = SimpleNamespace(request=request)
    _record_render(process, _render_record())
    waiting = asyncio.create_task(process.wait_for_vehicle_render("hero-gt", after_generation=1))
    await asyncio.sleep(0)
    process._record_output("PLAYGODOT_PREPARING_FIRST_FRAME")
    _record_render(process, _render_record(2, "graybox"))
    await asyncio.sleep(0)
    assert not waiting.done(), "A different vehicle must not satisfy the pending selection"
    _record_render(process, _render_record(3, "hero-gt"))
    assert (await waiting)["generation"] == 3
    request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["no_record", "stale", "wrong_asset", "pre_draw_only"])
async def test_missing_or_stale_render_completion_times_out(tmp_path: Path, mode: str) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    generation = 0
    if mode == "stale":
        _record_render(process, _render_record())
        generation = 1
    elif mode == "wrong_asset":
        _record_render(process, _render_record(1, "hero-gt"))
    elif mode == "pre_draw_only":
        process._record_output('PLAYGODOT_VEHICLE_PRE_DRAW {"asset_id":"endurance-sedan"}')
    with pytest.raises(TimeoutError, match="separate 0.01s render preparation"):
        await process.wait_for_vehicle_render(
            "endurance-sedan", after_generation=generation, timeout=0.01,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"generation": 0}, {"generation": 2}, {"generation": 65},
    {"asset_id": "unclaimed"}, {"vehicle_instance_id": 0}, {"panel_instance_id": -1},
    {"camera_instance_id": True}, {"viewport_instance_id": 2**63},
    {"post_draw_usec": 999}, {"post_process_frame": 2}, {"post_physics_frame": 5},
    {"post_drawn_frame": 2}, {"pre_draw_usec": float("nan")}, {"extra": 1},
])
async def test_malformed_or_mismatched_render_records_fail_closed(
    tmp_path: Path, changes: dict,
) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    _record_render(process, {**_render_record(), **changes})
    with pytest.raises(ProtocolError, match="Invalid vehicle render preparation"):
        await process.wait_for_vehicle_render("endurance-sedan", after_generation=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ["{}", "[]", "not json", '"' + "x" * 4_096 + '"'])
async def test_invalid_render_payload_is_not_ready(tmp_path: Path, payload: str) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    process._record_output("PLAYGODOT_VEHICLE_RENDERED " + payload)
    with pytest.raises(ProtocolError):
        await process.wait_for_vehicle_render("endurance-sedan", after_generation=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["vehicle_instance_id", "panel_instance_id"])
async def test_new_generation_cannot_reuse_a_retired_instance(
    tmp_path: Path, identity: str,
) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    first = _render_record()
    _record_render(process, first)
    _record_render(process, _render_record(2, "graybox"))
    _record_render(process, {**_render_record(3), identity: first[identity]})
    with pytest.raises(ProtocolError, match="reused a previous body or panel"):
        await process.wait_for_vehicle_render("endurance-sedan", after_generation=2)


@pytest.mark.asyncio
async def test_duplicate_generation_and_engine_limit_failure_reject(tmp_path: Path) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    _record_render(process, _render_record())
    _record_render(process, _render_record())
    with pytest.raises(ProtocolError, match="generation is repeated"):
        await process.wait_for_vehicle_render("endurance-sedan", after_generation=1)
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    process._record_output("PLAYGODOT_VEHICLE_RENDER_FAILED record limit exceeded")
    with pytest.raises(ProtocolError, match="record limit exceeded"):
        await process.wait_for_vehicle_render("endurance-sedan", after_generation=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {"asset_id": "unclaimed"}, {"after_generation": True}, {"after_generation": -1},
    {"after_generation": 1}, {"timeout": 0}, {"timeout": -1}, {"timeout": 60.01},
    {"timeout": float("inf")}, {"timeout": float("nan")}, {"timeout": True}, {"timeout": "60"},
])
async def test_invalid_render_preparation_bounds_reject(tmp_path: Path, arguments: dict) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    with pytest.raises(ValueError):
        await process.wait_for_vehicle_render(**{
            "asset_id": "endurance-sedan", "after_generation": 0, **arguments,
        })


@pytest.mark.asyncio
async def test_eof_wakes_render_waiter_and_retains_diagnostics(tmp_path: Path) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route", log_path=tmp_path / "engine.log")
    stream = asyncio.StreamReader()
    process.process = SimpleNamespace(stdout=stream)
    waiting = asyncio.create_task(process.wait_for_vehicle_render("hero-gt", after_generation=0))
    await asyncio.sleep(0)
    stream.feed_data(b"engine stopped before rendering new vehicle\n")
    stream.feed_eof()
    await process._drain_output()
    with pytest.raises(RuntimeError, match="closed stdout"):
        await asyncio.wait_for(waiting, 1)
    assert "stopped before rendering" in (tmp_path / "engine.log").read_text()


@pytest.mark.asyncio
async def test_cancelled_render_wait_does_not_consume_later_record(tmp_path: Path) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    waiting = asyncio.create_task(process.wait_for_vehicle_render("hero-gt", after_generation=0))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    _record_render(process, _render_record(1, "hero-gt"))
    assert (await process.wait_for_vehicle_render("hero-gt", after_generation=0))["generation"] == 1


@pytest.mark.asyncio
async def test_shutdown_wakes_pending_render_waiter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    monkeypatch.setattr(process, "_stop_process", AsyncMock())
    waiting = asyncio.create_task(process.wait_for_vehicle_render("hero-gt", after_generation=0))
    await asyncio.sleep(0)
    await process.stop()
    with pytest.raises(RuntimeError, match="Godot stopped"):
        await asyncio.wait_for(waiting, 1)
