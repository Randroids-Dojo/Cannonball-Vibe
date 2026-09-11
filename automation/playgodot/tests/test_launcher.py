from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cannonball_playgodot import PlayGodotProcess


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
