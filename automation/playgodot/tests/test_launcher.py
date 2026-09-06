from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cannonball_playgodot import PlayGodotProcess


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
