"""Prepare the actual semantic-test renderer before timing interactive behavior."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from .launcher import PlayGodotProcess


async def warmup(repo_root: Path, output: Path) -> None:
    package_root = repo_root / ".tools/scenarios/official-corridor"
    pointer = json.loads((package_root / "current-package.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    started = asyncio.get_running_loop().time()
    # Resource import is headless and cannot warm up a graphics driver's
    # pipelines. The first rendered launch pays that cost on the software
    # CI GPUs. Keep it outside the interactive tests' unchanged 20s startup
    # and request/settling bounds, with its own explicit, failing deadline.
    process = PlayGodotProcess(
        repo_root,
        package_root / pointer["root_relative_path"],
        capabilities=("read", "screenshot"),
        startup_timeout=120,
        request_timeout=120,
        transcript=output / "renderer-warmup.jsonl",
        log_path=output / "renderer-warmup-godot.log",
    )
    async with asyncio.timeout(180):
        async with process as client:
            state = (await client.describe("camera.chase.rig"))["test_state"]
            if not state.get("target_valid") or not state.get("active"):
                raise RuntimeError("Renderer warm-up did not load the active chase camera")
            capture = await client.screenshot(output / "renderer-warmup.png")
            if capture["bytes"] <= 0 or capture["width"] < 960 or capture["height"] < 540:
                raise RuntimeError("Renderer warm-up did not produce the expected viewport")
    result = {
        "renderer": "gl_compatibility",
        "graybox_vehicle": True,
        "graybox_environment": True,
        "startup_seconds": process.startup_elapsed_seconds,
        "elapsed_seconds": asyncio.get_running_loop().time() - started,
        "screenshot": capture,
    }
    (output / "renderer-warmup-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"CANNONBALL_PLAYGODOT_WARMUP_OK elapsed_s={result['elapsed_seconds']:.3f}")


if __name__ == "__main__":
    asyncio.run(warmup(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
