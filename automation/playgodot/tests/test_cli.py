from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cannonball_playgodot.cli import _load_plan, _run_plan


class _PlanClient:
    def __init__(self) -> None:
        self.clicked = asyncio.Event()

    async def request(self, method: str, params: dict) -> dict:
        if method == "signal.wait":
            await asyncio.wait_for(self.clicked.wait(), 1)
            return {"signal": params["signal"]}
        if method == "input.click":
            self.clicked.set()
            return {"automation_id": params["automation_id"]}
        return {"automation_id": params["automation_id"]}


@pytest.mark.asyncio
async def test_jsonl_plan_defers_wait_then_correlates_click(tmp_path: Path) -> None:
    plan = tmp_path / "plan.jsonl"
    plan.write_text(
        "\n".join(
            (
                '{"method":"signal.wait","params":{"automation_id":"button","signal":"pressed"},"defer":true}',
                '{"method":"input.click","params":{"automation_id":"button"}}',
                '{"method":"ui.describe","params":{"automation_id":"hud.speed"}}',
            )
        )
        + "\n"
    )

    results = await _run_plan(_PlanClient(), _load_plan(plan))

    assert [result["line"] for result in results] == [1, 2, 3]
    assert results[0]["result"] == {"signal": "pressed"}
    assert results[1]["result"] == {"automation_id": "button"}


def test_cli_process_failure_is_structured_json(tmp_path: Path) -> None:
    route = tmp_path / "route.cbrg"
    route.write_bytes(b"fixture")
    environment = os.environ.copy()
    environment["GODOT_BIN"] = str(tmp_path / "missing-godot")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cannonball_playgodot.cli",
            "--route-package",
            str(route),
            "capabilities",
        ],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert result.returncode == 6
    assert json.loads(result.stderr)["error"]["name"] == "PROCESS"
