from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .client import PlayGodotError, ProtocolError
from .launcher import PlayGodotProcess


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect Cannonball through semantic Godot UI")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--route-package", type=Path, required=True)
    parser.add_argument("--transcript", type=Path)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("capabilities")
    tree = subcommands.add_parser("tree")
    tree.add_argument("--max-depth", type=int, default=8)
    tree.add_argument("--max-nodes", type=int, default=512)
    describe = subcommands.add_parser("describe")
    describe.add_argument("automation_id")
    screenshot = subcommands.add_parser("screenshot")
    screenshot.add_argument("destination", type=Path)
    screenshot.add_argument("--automation-id")
    click = subcommands.add_parser("click")
    click.add_argument("automation_id")
    action = subcommands.add_parser("action")
    action.add_argument("action")
    action.add_argument("state", choices=("press", "release"))
    key = subcommands.add_parser("key")
    key.add_argument("key")
    key.add_argument("state", choices=("press", "release"))
    signal = subcommands.add_parser("signal")
    signal.add_argument("automation_id")
    signal.add_argument("signal")
    signal.add_argument("--timeout-ms", type=int, default=1_000)
    plan = subcommands.add_parser("run")
    plan.add_argument("plan", type=Path)
    return parser


def _load_plan(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not isinstance(item.get("method"), str):
            raise ValueError(f"Invalid plan entry on line {line_number}")
        params = item.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f"Invalid plan params on line {line_number}")
        entries.append(
            {
                "line": line_number,
                "method": item["method"],
                "params": params,
                "defer": item.get("defer", False) is True,
            }
        )
    return entries


async def _run_plan(client, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    deferred: list[tuple[int, str, asyncio.Task[Any]]] = []
    try:
        for item in entries:
            if item["defer"]:
                deferred.append(
                    (
                        item["line"],
                        item["method"],
                        asyncio.create_task(client.request(item["method"], item["params"])),
                    )
                )
                await asyncio.sleep(0)
                continue
            results.append(
                {
                    "line": item["line"],
                    "method": item["method"],
                    "result": await client.request(item["method"], item["params"]),
                }
            )
        for line_number, method, task in deferred:
            results.append(
                {"line": line_number, "method": method, "deferred": True, "result": await task}
            )
        return sorted(results, key=lambda item: item["line"])
    finally:
        for _, _, task in deferred:
            if not task.done():
                task.cancel()
        await asyncio.gather(*(task for _, _, task in deferred), return_exceptions=True)


async def _run(arguments: argparse.Namespace) -> int:
    capabilities = ["read"]
    plan = _load_plan(arguments.plan) if arguments.command == "run" else []
    plan_methods = {entry["method"] for entry in plan}
    if arguments.command == "screenshot" or any(
        method.startswith("screenshot.") for method in plan_methods
    ):
        capabilities.append("screenshot")
    if arguments.command in {"click", "action", "key"} or any(
        method.startswith("input.") for method in plan_methods
    ):
        capabilities.append("input")
    process = PlayGodotProcess(
        arguments.repo,
        arguments.route_package,
        capabilities=tuple(capabilities),
        transcript=arguments.transcript,
    )
    async with process as client:
        if arguments.command == "capabilities":
            result = await client.request("session.capabilities")
        elif arguments.command == "tree":
            result = await client.tree(max_depth=arguments.max_depth, max_nodes=arguments.max_nodes)
        elif arguments.command == "describe":
            result = await client.describe(arguments.automation_id)
        elif arguments.command == "screenshot":
            result = await client.screenshot(
                arguments.destination, automation_id=arguments.automation_id
            )
        elif arguments.command == "click":
            result = await client.request("input.click", {"automation_id": arguments.automation_id})
        elif arguments.command == "action":
            result = await client.request(
                "input.action", {"action": arguments.action, "state": arguments.state}
            )
        elif arguments.command == "key":
            result = await client.request(
                "input.key", {"key": arguments.key, "state": arguments.state}
            )
        elif arguments.command == "signal":
            result = await client.request(
                "signal.wait",
                {
                    "automation_id": arguments.automation_id,
                    "signal": arguments.signal,
                    "timeout_ms": arguments.timeout_ms,
                },
            )
        else:
            result = await _run_plan(client, plan)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> int:
    try:
        return asyncio.run(_run(_parser().parse_args()))
    except PlayGodotError as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {"code": error.code, "name": error.name, "message": error.message},
                }
            ),
            file=sys.stderr,
        )
        return 4
    except TimeoutError as error:
        print(
            json.dumps({"ok": False, "error": {"name": "TIMEOUT", "message": str(error)}}),
            file=sys.stderr,
        )
        return 5
    except ProtocolError as error:
        print(
            json.dumps({"ok": False, "error": {"name": "PROTOCOL", "message": str(error)}}),
            file=sys.stderr,
        )
        return 3
    except (FileNotFoundError, RuntimeError) as error:
        print(
            json.dumps({"ok": False, "error": {"name": "PROCESS", "message": str(error)}}),
            file=sys.stderr,
        )
        return 6
    except (ConnectionError, OSError) as error:
        print(
            json.dumps({"ok": False, "error": {"name": "PROTOCOL", "message": str(error)}}),
            file=sys.stderr,
        )
        return 3
    except (ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps({"ok": False, "error": {"name": "USAGE", "message": str(error)}}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
