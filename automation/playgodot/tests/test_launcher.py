from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cannonball_playgodot import PlayGodotProcess
from cannonball_playgodot.client import ProtocolError
from cannonball_playgodot.launcher import ShutdownError


@pytest.mark.parametrize("vehicle", [None, "endurance-sedan", "hero-gt", "graybox"])
@pytest.mark.parametrize("production_vehicle", [False, True])
@pytest.mark.asyncio
async def test_explicit_vehicle_and_disposable_profile_preserve_default_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vehicle: str | None,
    production_vehicle: bool,
) -> None:
    route = tmp_path / "fixture.cbrg"
    route.write_bytes(b"fixture")
    child = SimpleNamespace(stdout=asyncio.StreamReader(), pid=100, returncode=0)
    child.stdout.feed_eof()
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setenv("HOME", str(tmp_path / "real-user-home"))
    process = PlayGodotProcess(
        tmp_path, route, godot_bin=Path(sys.executable), vehicle=vehicle,
        isolate_user_data=vehicle is not None, production_vehicle=production_vehicle,
    )
    monkeypatch.setattr(process, "_read_ready", AsyncMock(side_effect=RuntimeError("stop probe")))
    with pytest.raises(RuntimeError, match="stop probe"):
        await process.start()
    command = spawn.call_args.args
    environment = spawn.call_args.kwargs["env"]
    renderer_index = command.index("--rendering-method")
    assert command.count("--rendering-method") == 1
    assert renderer_index < command.index("--")
    assert command[renderer_index + 1] == "gl_compatibility"
    assert process.rendering_method == "gl_compatibility"
    assert process.window_size is None
    assert "--windowed" not in command and "--resolution" not in command
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
    assert "shutdown" in environment["PLAYGODOT_CAPABILITIES"].split(",")
    assert process.capabilities == ("read",)
    assert environment["PLAYGODOT_TOKEN"] not in " ".join(command)


def test_unknown_explicit_vehicle_is_rejected_before_launch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown explicit PlayGodot vehicle"):
        PlayGodotProcess(tmp_path, tmp_path / "fixture.cbrg", vehicle="unclaimed")


@pytest.mark.parametrize("rendering_method", ["gl_compatibility", "forward_plus"])
@pytest.mark.parametrize("xvfb", [False, True])
@pytest.mark.asyncio
async def test_explicit_renderer_changes_only_the_engine_renderer_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rendering_method: str,
    xvfb: bool,
) -> None:
    monkeypatch.setattr("cannonball_playgodot.launcher.platform.system", lambda: "Linux")
    monkeypatch.setenv("PLAYGODOT_XVFB", "1" if xvfb else "0")
    route = tmp_path / "fixture.cbrg"
    route.write_bytes(b"fixture")
    child = SimpleNamespace(stdout=asyncio.StreamReader(), pid=100, returncode=0)
    child.stdout.feed_eof()
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    process = PlayGodotProcess(
        tmp_path, route, godot_bin=Path(sys.executable), vehicle="endurance-sedan",
        isolate_user_data=True, rendering_method=rendering_method,
    )
    monkeypatch.setattr(process, "_read_ready", AsyncMock(side_effect=RuntimeError("stop probe")))
    with pytest.raises(RuntimeError, match="stop probe"):
        await process.start()
    spawn.assert_awaited_once()
    command = spawn.call_args.args
    renderer_index = command.index("--rendering-method")
    assert command.count("--rendering-method") == 1
    assert renderer_index < command.index("--")
    assert command[renderer_index + 1] == rendering_method
    # Keep the configured executable, including a virtual-environment symlink.
    prefix = ("xvfb-run", "-a") if xvfb else ()
    assert command[:len(prefix) + 1] == (*prefix, str(Path(sys.executable)))
    assert "--vehicle=endurance-sedan" in command
    assert "--graybox-vehicle" not in command
    assert f"--route-package={route.resolve()}" in command
    assert process.capabilities == ("read",)
    assert process.request_timeout == 10.0 and process.startup_timeout == 20.0
    environment = spawn.call_args.kwargs["env"]
    assert set(environment["PLAYGODOT_CAPABILITIES"].split(",")) == {"read", "shutdown"}
    assert environment["PLAYGODOT_TOKEN"] not in " ".join(command)
    assert process._runtime_directory is None
    assert not Path(environment["HOME"]).exists()


@pytest.mark.parametrize("rendering_method", [
    None, "", "mobile", "Forward+", "forward_plus --quit", ["forward_plus"], False, 0,
])
def test_invalid_renderer_is_rejected_before_engine_discovery_or_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rendering_method: object,
) -> None:
    def forbidden_discovery():
        pytest.fail("Invalid renderer reached engine discovery")

    monkeypatch.setattr(PlayGodotProcess, "_godot_from_environment", forbidden_discovery)
    spawn = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(ValueError, match="Unknown PlayGodot rendering method"):
        PlayGodotProcess(tmp_path, tmp_path / "fixture.cbrg", rendering_method=rendering_method)
    spawn.assert_not_called()


@pytest.mark.parametrize("window_size", [(960, 540), (2560, 1440), (7680, 4320)])
@pytest.mark.asyncio
async def test_explicit_window_size_stays_in_engine_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window_size: tuple[int, int],
) -> None:
    route = tmp_path / "fixture.cbrg"
    route.write_bytes(b"fixture")
    child = SimpleNamespace(stdout=asyncio.StreamReader(), pid=100, returncode=0)
    child.stdout.feed_eof()
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    process = PlayGodotProcess(
        tmp_path, route, godot_bin=Path(sys.executable), rendering_method="forward_plus",
        window_size=window_size,
    )
    monkeypatch.setattr(process, "_read_ready", AsyncMock(side_effect=RuntimeError("stop probe")))
    with pytest.raises(RuntimeError, match="stop probe"):
        await process.start()
    spawn.assert_awaited_once()
    command = spawn.call_args.args
    separator = command.index("--")
    assert command.count("--windowed") == command.count("--resolution") == 1
    assert command.index("--windowed") < separator
    size_index = command.index("--resolution")
    assert size_index < separator
    assert command[size_index + 1] == f"{window_size[0]}x{window_size[1]}"
    assert command[command.index("--rendering-method") + 1] == "forward_plus"
    assert "--vehicle=graybox" in command and "--graybox-vehicle" in command
    assert f"--route-package={route.resolve()}" in command
    assert process.window_size == window_size and process.capabilities == ("read",)
    assert process.request_timeout == 10 and process.startup_timeout == 20
    assert process._runtime_directory is None


@pytest.mark.parametrize("window_size", [
    (), (1280,), (1280, 720, 1), (959, 540), (960, 539), (7681, 4320), (7680, 4321),
    (1280.0, 720), (1280, True), [1280, 720], "1280x720", "1280x720 --quit",
])
def test_invalid_window_size_is_rejected_before_engine_discovery_or_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window_size: object,
) -> None:
    def forbidden_discovery():
        pytest.fail("Invalid window size reached engine discovery")

    monkeypatch.setattr(PlayGodotProcess, "_godot_from_environment", forbidden_discovery)
    spawn = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(ValueError, match="Invalid PlayGodot window size"):
        PlayGodotProcess(tmp_path, tmp_path / "fixture.cbrg", window_size=window_size)
    spawn.assert_not_called()


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


class _Child:
    def __init__(self) -> None:
        self.pid = 12345
        self.returncode: int | None = None
        self.stdout = asyncio.StreamReader()
        self.exited = asyncio.Event()

    async def wait(self) -> int:
        await self.exited.wait()
        assert self.returncode is not None
        return self.returncode

    def finish(self, code: int = 0, *, eof: bool = True) -> None:
        self.returncode = code
        self.exited.set()
        if eof:
            self.stdout.feed_eof()


def _cleanup_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from cannonball_playgodot import launcher

    process = PlayGodotProcess(tmp_path, tmp_path / "route", log_path=tmp_path / "native.log")
    process.log_path.write_text("")
    process.process = child = _Child()
    process._shutdown_token = "private-test-token-do-not-persist"
    process._shutdown_endpoint = ("127.0.0.1", 1234)
    signals = []
    monkeypatch.setattr(process, "_signal_process", lambda *, force: signals.append(force))
    # Scaled wall-clock controls test the same absolute phase arithmetic. The
    # separate full-budget control below retains the actual 5+1+1+1 schedule.
    monkeypatch.setattr(launcher, "SHUTDOWN_PHASE_SECONDS", (.10, .05, .05, .25))
    monkeypatch.setattr(launcher, "SHUTDOWN_TIMEOUT_SECONDS", .45)
    return process, child, signals


def _quit_marker(process: PlayGodotProcess) -> None:
    process._record_output('PLAYGODOT_QUIT {"pending_waits_before":1,"held_inputs_before":1,'
                           '"pending_waits_after":0,"held_inputs_after":0}')


@pytest.mark.asyncio
async def test_clean_owned_quit_retains_native_exit_log_and_idempotent_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    process, child, signals = _cleanup_fixture(tmp_path, monkeypatch)

    async def quit_child(_deadline, record):
        record.update(quit_requested=True, quit_acknowledged=True)
        _quit_marker(process)
        child.finish()

    monkeypatch.setattr(process, "_request_quit", quit_child)
    await process.stop()
    first = process.teardown_result
    await process.stop()
    assert process.teardown_result is first and process.process is None
    assert first["status"] == "passed" and first["exit_status"] == 0
    assert first["output_eof"] and first["quit_acknowledged"] and not signals
    assert first["native_log"]["bytes"] == process.log_path.stat().st_size
    serialized = process.log_path.with_suffix(".shutdown.json").read_text()
    assert "private-test-token" not in serialized
    assert json.loads(serialized)["native_log"]["sha256"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["nonzero", "missing_marker", "native_error", "leak",
                                 "bad_resources", "drain_open", "prior_error"])
async def test_exit_zero_alone_cannot_hide_shutdown_or_incomplete_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    process, child, _signals = _cleanup_fixture(tmp_path, monkeypatch)
    if mode == "prior_error":
        process._record_output("ERROR: separate pre-existing fixture failure")

    async def quit_child(_deadline, record):
        record.update(quit_requested=True, quit_acknowledged=True)
        if mode != "missing_marker":
            _quit_marker(process)
        if mode == "native_error":
            process._record_output("ERROR: resource shutdown failed")
        if mode == "leak":
            process._record_output("WARNING: ObjectDB instances leaked at exit")
        if mode == "bad_resources":
            process._record_output('PLAYGODOT_QUIT {"pending_waits_after":1}')
        child.finish(1 if mode == "nonzero" else 0, eof=mode != "drain_open")

    monkeypatch.setattr(process, "_request_quit", quit_child)
    if mode == "prior_error":
        await process.stop()
        assert process.teardown_result["diagnostics"][0]["shutdown"] is False
    else:
        with pytest.raises(ShutdownError):
            await process.stop()
        assert process.teardown_result["status"] == "failed"
    if mode == "drain_open":
        assert process.teardown_result["output_eof"] is False
    if mode != "drain_open":
        assert process.log_path.with_suffix(".shutdown.json").is_file()
    else:
        assert not process.teardown_result["bookkeeping_completed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_on", ["terminate", "kill", "never"])
async def test_fallback_is_bounded_and_never_reported_as_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finish_on: str,
) -> None:
    process, child, signals = _cleanup_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(process, "_request_quit", AsyncMock(side_effect=TimeoutError))

    def signal_child(*, force):
        signals.append(force)
        if (finish_on == "kill" and force) or (finish_on == "terminate" and not force):
            child.finish(0)  # Even a fallback exit0 is not a clean quit.

    monkeypatch.setattr(process, "_signal_process", signal_child)
    started = asyncio.get_running_loop().time()
    with pytest.raises(ShutdownError) as first:
        await process.stop()
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 1 and process.teardown_result["status"] == "failed"
    assert process.teardown_result["fallback"][0] == "terminate"
    if finish_on == "never":
        assert process.process is child and child.returncode is None
        assert process.teardown_result["exit_status"] is None
        assert signals == [False, True]
    with pytest.raises(ShutdownError) as repeated:
        await process.stop()
    assert repeated.value is first.value
    child.finish(0)  # Release the fake wait fixture, not a claimed native result.


@pytest.mark.asyncio
@pytest.mark.parametrize("original", [RuntimeError("original assertion"),
                                     asyncio.CancelledError("original cancellation")])
async def test_original_failure_survives_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, original: BaseException,
) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    monkeypatch.setattr(process, "stop", AsyncMock(side_effect=ShutdownError("teardown failure")))
    await process.__aexit__(type(original), original, None)
    assert any("ShutdownError" in note for note in original.__notes__)
    with pytest.raises(ShutdownError):
        await process.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_same_cleanup_and_keeps_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    process, child, signals = _cleanup_fixture(tmp_path, monkeypatch)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def quit_child(_deadline, record):
        entered.set()
        await release.wait()
        _quit_marker(process)
        child.finish()

    monkeypatch.setattr(process, "_request_quit", quit_child)
    stop = asyncio.create_task(process.stop())
    await entered.wait()
    stop.cancel("first cancellation")
    await asyncio.sleep(0)
    stop.cancel("second cancellation")
    release.set()
    with pytest.raises(asyncio.CancelledError, match="first cancellation"):
        await stop
    assert process.teardown_result["status"] == "passed" and not signals
    await process.stop()


@pytest.mark.asyncio
async def test_quit_session_grant_does_not_change_ordinary_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    process, _child, _signals = _cleanup_fixture(tmp_path, monkeypatch)
    writer = SimpleNamespace(transport=SimpleNamespace(abort=lambda: None))
    owner = SimpleNamespace(_writer=writer, request=AsyncMock(return_value={"quitting": True}),
                            close=AsyncMock())
    connect = AsyncMock(side_effect=[
        ProtocolError("PlayGodot closed the connection without a response"), owner,
    ])
    monkeypatch.setattr("cannonball_playgodot.launcher.PlayGodotClient.connect", connect)
    record = {"connection_turnover_retries": 0}
    deadline = asyncio.get_running_loop().time() + .2
    await process._request_quit(deadline, record)
    assert process.capabilities == ("read",)
    assert all(call.kwargs["capabilities"] == ("shutdown",) for call in connect.call_args_list)
    assert connect.call_args_list[1].kwargs["timeout"] < connect.call_args_list[0].kwargs["timeout"]
    assert record["connection_turnover_retries"] == 1 and record["quit_acknowledged"]
    owner.request.assert_awaited_once_with("session.quit")
    assert "private-test-token" not in json.dumps(record)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ProtocolError("invalid response"),
                                     ValueError("unsafe endpoint")])
async def test_quit_does_not_retry_arbitrary_protocol_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception,
) -> None:
    process, _child, _signals = _cleanup_fixture(tmp_path, monkeypatch)
    connect = AsyncMock(side_effect=error)
    monkeypatch.setattr("cannonball_playgodot.launcher.PlayGodotClient.connect", connect)
    with pytest.raises(type(error)):
        await process._request_quit(asyncio.get_running_loop().time() + .2,
                                    {"connection_turnover_retries": 0})
    connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_eight_second_deadline_includes_a_stuck_process_and_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record_property,
) -> None:
    from cannonball_playgodot import launcher

    assert launcher.SHUTDOWN_PHASE_SECONDS == (5.0, 1.0, 1.0, 1.0)
    assert launcher.SHUTDOWN_TIMEOUT_SECONDS == 8.0
    process = PlayGodotProcess(tmp_path, tmp_path / "route", log_path=tmp_path / "stuck.log")
    process.log_path.write_text("")
    process.process = child = _Child()
    monkeypatch.setattr(process, "_request_quit", AsyncMock(side_effect=TimeoutError))
    signals, deadlines = [], []
    monkeypatch.setattr(process, "_signal_process", lambda *, force: signals.append(force))
    before = process._before

    async def observe_deadline(awaitable, deadline):
        deadlines.append(deadline - process.teardown_result["started_monotonic_seconds"])
        return await before(awaitable, deadline)

    monkeypatch.setattr(process, "_before", observe_deadline)
    started = asyncio.get_running_loop().time()
    try:
        with pytest.raises(ShutdownError):
            await process.stop()
        elapsed = asyncio.get_running_loop().time() - started
        record_property("shutdown_wall_elapsed_seconds", elapsed)
        # Event-loop dispatch can resume late. Verify the deadlines passed to
        # the real waits; a late failed owner remains a failure, never success.
        assert elapsed >= 7.9
        assert deadlines == pytest.approx([5.0, 6.0, 7.0, 8.0], abs=1e-8)
        result = process.teardown_result
        assert result["phase_seconds"] == [5.0, 1.0, 1.0, 1.0]
        assert result["total_budget_seconds"] == 8.0
        assert signals == [False, True] and result["fallback"] == ["terminate", "kill"]
        assert process.process is child and result["status"] == "failed"
        assert result["exit_status"] is None and not result["output_eof"]
        assert not result["bookkeeping_completed"]
        assert {row["phase"] for row in result["phase_errors"]} >= {"output-drain", "bookkeeping"}
    finally:
        child.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize("completion_elapsed, passed", [
    (7.99, True), (8.0, True), (8.000001, False), (8.324299, False),
])
async def test_owner_finalization_never_passes_beyond_absolute_eight_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, completion_elapsed: float, passed: bool,
) -> None:
    from cannonball_playgodot import launcher

    assert launcher.SHUTDOWN_TIMEOUT_SECONDS == 8.0
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    process.process = child = _Child()
    loop = asyncio.get_running_loop()
    clock = [1000.0]
    before = process._before

    async def quit_child(_deadline, record):
        record.update(quit_requested=True, quit_acknowledged=True)
        _quit_marker(process)
        child.finish()

    def bookkeeping(_record):
        future = loop.create_future()
        future.set_result({"profile_removed": False})
        process._bookkeeping_future = future
        return future

    async def observe_completion(awaitable, deadline):
        result = await before(awaitable, deadline)
        if process._bookkeeping_future is not None:
            # Advance only the owner's observed completion time, after the
            # successful wait, so every other success prerequisite holds.
            clock[0] = 1000.0 + completion_elapsed
        return result

    with monkeypatch.context() as patch:
        patch.setattr(
            launcher.asyncio, "get_running_loop", lambda: SimpleNamespace(time=lambda: clock[0]),
        )
        patch.setattr(process, "_request_quit", quit_child)
        patch.setattr(process, "_start_bookkeeping", bookkeeping)
        patch.setattr(process, "_before", observe_completion)
        if passed:
            await process.stop()
        else:
            with pytest.raises(ShutdownError):
                await process.stop()
    result = process.teardown_result
    assert result["elapsed_seconds"] == pytest.approx(completion_elapsed, abs=1e-8)
    assert result["total_budget_seconds"] == 8.0
    assert result["exit_status"] == 0 and result["output_eof"] and result["bookkeeping_completed"]
    assert not result["fallback"] and not result["phase_errors"] and not result["diagnostics"]
    assert result["unfinished_operations"] == 0 and process.process is None
    assert result["status"] == ("passed" if passed else "failed")


@pytest.mark.asyncio
async def test_phase_timeout_does_not_wait_for_uncooperative_cancellation(
    tmp_path: Path,
) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route")
    release = asyncio.Event()

    async def uncooperative():
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        await process._before(uncooperative(), started + .02)
    assert asyncio.get_running_loop().time() - started < .15
    assert any(not task.done() for task in process._cleanup_waits)
    release.set()
    await asyncio.gather(*process._cleanup_waits)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["session-close", "graceful-exit", "terminate", "kill", "drain"])
async def test_cancellation_in_each_cleanup_phase_keeps_bounded_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str,
) -> None:
    process, child, signals = _cleanup_fixture(tmp_path, monkeypatch)
    stop_task = None

    def cancel():
        assert stop_task is not None
        stop_task.cancel("original phase cancellation")

    async def close():
        cancel()

    if phase == "session-close":
        process.client = SimpleNamespace(close=close, _writer=SimpleNamespace(
            transport=SimpleNamespace(abort=lambda: None)))

    async def quit_child(_deadline, record):
        if phase in ("terminate", "kill"):
            raise TimeoutError
        _quit_marker(process)
        if phase == "graceful-exit":
            asyncio.get_running_loop().call_soon(cancel)
            asyncio.get_running_loop().call_later(.005, child.finish)
        elif phase == "drain":
            child.finish(eof=False)
            asyncio.get_running_loop().call_soon(cancel)
            asyncio.get_running_loop().call_later(.005, child.stdout.feed_eof)
        else:
            child.finish()

    def signal_child(*, force):
        signals.append(force)
        if (phase == "kill" and force) or (phase == "terminate" and not force):
            cancel()
            child.finish()

    monkeypatch.setattr(process, "_request_quit", quit_child)
    monkeypatch.setattr(process, "_signal_process", signal_child)
    stop_task = asyncio.create_task(process.stop())
    with pytest.raises(asyncio.CancelledError, match="original phase cancellation") as caught:
        await stop_task
    assert process.process is None and child.returncode == 0
    assert process.teardown_result["output_eof"]
    assert process.teardown_result["elapsed_seconds"] < 1
    if phase in ("terminate", "kill"):
        assert process.teardown_result["status"] == "failed"
        assert any("ShutdownError" in note for note in caught.value.__notes__)
    else:
        assert process.teardown_result["status"] == "passed"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["clean", "error_after_acceptance", "no_quit", "nonzero"])
async def test_already_exited_child_requires_actual_quit_and_diagnostic_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    process, child, signals = _cleanup_fixture(tmp_path, monkeypatch)
    if mode != "no_quit":
        process._record_output("PLAYGODOT_QUIT_ACCEPTED")
        if mode == "error_after_acceptance":
            process._record_output("ERROR: native input cleanup failed before owner stop")
        _quit_marker(process)
    child.finish(1 if mode == "nonzero" else 0)
    request = AsyncMock(side_effect=AssertionError("dead process must not receive an RPC"))
    monkeypatch.setattr(process, "_request_quit", request)
    if mode == "clean":
        await process.stop()
    else:
        with pytest.raises(ShutdownError):
            await process.stop()
    assert not signals
    request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("code,name", [(-32002, "AUTH_FAILED"), (-32003, "CAPABILITY_DENIED")])
async def test_owner_authentication_failures_are_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, name: str,
) -> None:
    from cannonball_playgodot.client import PlayGodotError

    process, _child, _signals = _cleanup_fixture(tmp_path, monkeypatch)
    connect = AsyncMock(side_effect=PlayGodotError(code, name, "denied"))
    monkeypatch.setattr("cannonball_playgodot.launcher.PlayGodotClient.connect", connect)
    record = {"connection_turnover_retries": 0}
    with pytest.raises(PlayGodotError):
        await process._request_quit(asyncio.get_running_loop().time() + .2, record)
    connect.assert_awaited_once()
    assert record == {"connection_turnover_retries": 0}


@pytest.mark.asyncio
async def test_new_start_cannot_overlap_unfinished_cleanup(tmp_path: Path) -> None:
    process = PlayGodotProcess(tmp_path, tmp_path / "route", godot_bin=Path(sys.executable))
    release = asyncio.Event()
    process._cleanup_task = asyncio.create_task(release.wait())
    with pytest.raises(RuntimeError, match="cleanup is still incomplete"):
        await process.start()
    release.set()
    await process._cleanup_task


@pytest.mark.asyncio
async def test_restarted_startup_failure_drains_new_output_and_keeps_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = tmp_path / "route"
    route.write_bytes(b"fixture")
    process = PlayGodotProcess(tmp_path, route, godot_bin=Path(sys.executable),
                               log_path=tmp_path / "restart.log")
    process._drain_task = asyncio.create_task(asyncio.sleep(0))
    await process._drain_task
    process.output.append("old child output")
    child = _Child()
    child.stdout.feed_data(b"new child native failure\n")
    child.finish(1)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    with pytest.raises(RuntimeError, match="Godot exited before PlayGodot was ready") as caught:
        await process.start()
    assert "new child native failure" in str(caught.value)
    assert "old child output" not in str(caught.value)
    assert process.teardown_result["exit_status"] == 1
    assert process.teardown_result["output_eof"] and process.process is None
    assert any("ShutdownError" in note for note in caught.value.__notes__)


@pytest.mark.asyncio
@pytest.mark.parametrize("native_exit_delay", [0.0, 0.05])
async def test_early_native_exit_uses_only_the_remaining_absolute_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, native_exit_delay: float,
) -> None:
    from cannonball_playgodot import launcher

    process, child, signals = _cleanup_fixture(tmp_path, monkeypatch)
    profile = tmp_path / "owned-profile"
    profile.mkdir()
    process._runtime_directory = profile
    release = threading.Event()
    remove = shutil.rmtree
    loop = asyncio.get_running_loop()
    deadlines = []
    before = process._before

    def bounded_slow_remove(path):
        assert path.samefile(profile)
        assert profile.resolve().is_relative_to(tmp_path.resolve())
        # Longer than the .25s final reservation, within the same .45s cap.
        loop.call_soon_threadsafe(loop.call_later, .30, release.set)
        assert release.wait(2), "The test must release its bookkeeping worker"
        remove(path)

    async def observe_deadline(awaitable, deadline):
        if process.process is None and process._bookkeeping_future is not None:
            deadlines.append(deadline - process.teardown_result["started_monotonic_seconds"])
        return await before(awaitable, deadline)

    async def quit_child(_deadline, record):
        await asyncio.sleep(native_exit_delay)
        record.update(quit_requested=True, quit_acknowledged=True)
        _quit_marker(process)
        child.finish()

    monkeypatch.setattr(launcher.shutil, "rmtree", bounded_slow_remove)
    monkeypatch.setattr(process, "_before", observe_deadline)
    monkeypatch.setattr(process, "_request_quit", quit_child)
    try:
        await process.stop()
    finally:
        release.set()
        if process._bookkeeping_future is not None:
            await asyncio.wait_for(asyncio.shield(process._bookkeeping_future), 1)
    result = process.teardown_result
    assert deadlines == pytest.approx([launcher.SHUTDOWN_TIMEOUT_SECONDS], abs=1e-8)
    assert result["status"] == "passed" and result["exit_status"] == 0
    assert result["bookkeeping_completed"] and not profile.exists()
    assert not signals and not result["phase_errors"]
    assert result["elapsed_seconds"] <= launcher.SHUTDOWN_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_slow_bookkeeping_cannot_block_or_write_late_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    process, child, _signals = _cleanup_fixture(tmp_path, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    profile = tmp_path / "owned-profile"
    profile.mkdir()
    process._runtime_directory = profile
    remove = shutil.rmtree

    def blocked_remove(path):
        assert path.samefile(profile)
        assert profile.resolve().is_relative_to(tmp_path.resolve())
        entered.set()
        assert release.wait(2), "The test must release its blocked filesystem fixture"
        remove(path)

    monkeypatch.setattr("cannonball_playgodot.launcher.shutil.rmtree", blocked_remove)

    async def quit_child(_deadline, _record):
        _quit_marker(process)
        child.finish()

    monkeypatch.setattr(process, "_request_quit", quit_child)
    started = asyncio.get_running_loop().time()
    try:
        with pytest.raises(ShutdownError):
            await process.stop()
        assert asyncio.get_running_loop().time() - started < 1
        assert entered.is_set() and not process._bookkeeping_future.done()
        assert process.teardown_result["status"] == "failed"
        assert not process.teardown_result["bookkeeping_completed"]
        # Shutdown bytes were flushed before the deliberately blocked profile
        # operation; neither the pipe drain nor the owner blocked on disk I/O.
        assert "PLAYGODOT_QUIT" in process.log_path.read_text()
        with pytest.raises(RuntimeError, match="cleanup is still incomplete"):
            await process.start()
    finally:
        release.set()
        await asyncio.wait_for(process._bookkeeping_future, 1)
    observation = json.loads(process.log_path.with_suffix(".shutdown.json").read_text())
    assert observation["status"] == "native-observation"
    assert observation["owner_finalization_required"]
    assert process.teardown_result["status"] == "failed", "A late write is never a final pass"


@pytest.mark.asyncio
async def test_shutdown_log_write_is_off_loop_and_failure_remains_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    process, child, _signals = _cleanup_fixture(tmp_path, monkeypatch)
    main_thread = threading.get_ident()
    original_open = Path.open

    def broken_log(path, *args, **kwargs):
        if path == process.log_path:
            assert threading.get_ident() != main_thread
            raise OSError("injected shutdown log I/O failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_log)

    async def quit_child(_deadline, _record):
        _quit_marker(process)
        child.finish()

    monkeypatch.setattr(process, "_request_quit", quit_child)
    with pytest.raises(ShutdownError):
        await process.stop()
    assert process.teardown_result["status"] == "failed"
    assert {"phase": "bookkeeping", "type": "OSError"} in process.teardown_result["phase_errors"]
    assert process.teardown_result["output_eof"] and process.process is None


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows MAX_PATH filesystem regression")
@pytest.mark.asyncio
async def test_owned_profile_removes_actual_long_shader_cache_without_relaxing_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    process, child, signals = _cleanup_fixture(tmp_path, monkeypatch)
    profile = tmp_path / "owned-profile"
    profile.mkdir()
    process._runtime_directory = profile
    cache = (profile / "appdata/Godot/app_userdata/Cannonball Run/shader_cache"
             / "CanvasOcclusionShaderRD" / ("b" * 64) / (("c" * 40) + ".vulkan.cache"))
    assert profile.resolve().is_relative_to(tmp_path.resolve())
    assert len(str(cache)) > 260
    extended_cache = Path("\\\\?\\" + str(cache))
    extended_cache.parent.mkdir(parents=True)
    extended_cache.write_bytes(b"actual long-name cleanup control")

    async def quit_child(_deadline, record):
        record.update(quit_requested=True, quit_acknowledged=True)
        _quit_marker(process)
        child.finish()

    monkeypatch.setattr(process, "_request_quit", quit_child)
    await process.stop()
    result = process.teardown_result
    assert result["status"] == "passed" and result["exit_status"] == 0
    assert result["output_eof"] and result["bookkeeping_completed"]
    assert not result["fallback"] and not result["phase_errors"] and not signals
    assert process._runtime_directory is None
    assert not profile.exists() and not extended_cache.exists()
    assert result["native_log"]["sha256"]
    observation = json.loads(process.log_path.with_suffix(".shutdown.json").read_text())
    assert observation["status"] == "native-observation"
    assert observation["owner_finalization_required"] is True


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows profile filesystem errors")
@pytest.mark.parametrize("mode", ["missing", "readonly"])
@pytest.mark.asyncio
async def test_windows_profile_path_fix_keeps_missing_and_permission_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    import stat

    process, child, _signals = _cleanup_fixture(tmp_path, monkeypatch)
    profile = tmp_path / "owned-profile"
    process._runtime_directory = profile
    cache = profile / "cache.bin"
    if mode == "readonly":
        profile.mkdir()
        cache.write_bytes(b"permission error must remain visible")
        cache.chmod(stat.S_IREAD)

    async def quit_child(_deadline, record):
        record.update(quit_requested=True, quit_acknowledged=True)
        _quit_marker(process)
        child.finish()

    monkeypatch.setattr(process, "_request_quit", quit_child)
    try:
        with pytest.raises(ShutdownError):
            await process.stop()
        result = process.teardown_result
        assert result["status"] == "failed" and result["exit_status"] == 0
        assert result["output_eof"] and not result["bookkeeping_completed"]
        expected = "FileNotFoundError" if mode == "missing" else "PermissionError"
        assert {"phase": "bookkeeping", "type": expected} in result["phase_errors"]
        assert process._runtime_directory == profile
    finally:
        if cache.exists():
            assert profile.resolve().is_relative_to(tmp_path.resolve())
            cache.chmod(stat.S_IWRITE | stat.S_IREAD)
            shutil.rmtree(profile)


@pytest.mark.skipif(os.name != "nt", reason="Windows owned-root cleanup guard")
@pytest.mark.parametrize("mode", ["relative", "symlink", "junction"])
@pytest.mark.asyncio
async def test_windows_cleanup_rejects_changed_root_before_recursive_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    from unittest.mock import Mock

    process, child, _signals = _cleanup_fixture(tmp_path, monkeypatch)
    profile = Path("relative-profile") if mode == "relative" else tmp_path / "owned-profile"
    process._runtime_directory = profile
    if mode != "relative":
        profile.mkdir()
        name = "is_symlink" if mode == "symlink" else "is_junction"
        original = getattr(Path, name)
        monkeypatch.setattr(Path, name, lambda path: True if path == profile else original(path))
    remove = Mock()
    monkeypatch.setattr("cannonball_playgodot.launcher.shutil.rmtree", remove)

    async def quit_child(_deadline, record):
        record.update(quit_requested=True, quit_acknowledged=True)
        _quit_marker(process)
        child.finish()

    monkeypatch.setattr(process, "_request_quit", quit_child)
    with pytest.raises(ShutdownError):
        await process.stop()
    remove.assert_not_called()
    assert {"phase": "bookkeeping", "type": "OSError"} in process.teardown_result["phase_errors"]
    assert process._runtime_directory == profile
