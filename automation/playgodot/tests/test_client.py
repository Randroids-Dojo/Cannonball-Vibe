from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cannonball_playgodot.client import PlayGodotClient, PlayGodotError, ProtocolError

GOLDEN_SESSION = Path(__file__).parent / "golden/v1/session.jsonl"


def _hello(capabilities: list[str] | None = None) -> dict:
    return {
        "protocol": "1.0",
        "engine": "4.7.1-stable (official)",
        "build": "debug",
        "capabilities": capabilities or ["read"],
        "limits": {
            "request_bytes": 65_536,
            "response_bytes": 2_000_000,
            "json_depth": 12,
            "tree_depth": 8,
            "tree_nodes": 512,
            "signal_wait_ms": 10_000,
            "screenshot_bytes": 1_400_000,
        },
    }


async def _serve_once(response_factory):
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while line := await reader.readline():
            request = json.loads(line)
            response = response_factory(request)
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


@pytest.mark.asyncio
async def test_connect_negotiates_then_returns_correlated_result() -> None:
    golden = [json.loads(line) for line in GOLDEN_SESSION.read_text().splitlines()]

    def responses(request):
        expected_request = golden.pop(0)
        assert expected_request == {"direction": "client", "message": request}
        response = golden.pop(0)
        assert response["direction"] == "server"
        return response["message"]

    server, port = await _serve_once(responses)
    async with server:
        client = await PlayGodotClient.connect("127.0.0.1", port, token="x" * 32)
        assert await client.request("session.ping") == {"ok": True}
        assert golden == []
        await client.close(abort=True)


@pytest.mark.asyncio
async def test_remote_errors_keep_machine_readable_identity() -> None:
    def responses(request):
        if request["method"] == "session.hello":
            return {"jsonrpc": "2.0", "id": request["id"], "result": _hello()}
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "error": {"code": -32003, "name": "CAPABILITY_DENIED", "message": "denied"},
        }

    server, port = await _serve_once(responses)
    async with server:
        client = await PlayGodotClient.connect("127.0.0.1", port, token="x" * 32)
        with pytest.raises(PlayGodotError, match="CAPABILITY_DENIED") as caught:
            await client.request("input.action", {"action": "accelerate", "state": "press"})
        assert caught.value.code == -32003
        await client.close(abort=True)


@pytest.mark.asyncio
async def test_client_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValueError, match="loopback"):
        await PlayGodotClient.connect("0.0.0.0", 1, token="x" * 32)


@pytest.mark.asyncio
async def test_client_rejects_malformed_response() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        writer.write(b"not-json\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        with pytest.raises(ProtocolError, match="malformed JSON"):
            await PlayGodotClient.connect("127.0.0.1", port, token="x" * 32)


@pytest.mark.asyncio
async def test_timeout_closes_session_instead_of_accepting_late_response() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = json.loads(await reader.readline())
        writer.write(
            json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": _hello()}).encode() + b"\n"
        )
        await writer.drain()
        await reader.readline()
        await asyncio.sleep(1)
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        client = await PlayGodotClient.connect("127.0.0.1", port, token="x" * 32, timeout=0.05)
        with pytest.raises(TimeoutError, match="timed out"):
            await client.request("signal.wait")
        with pytest.raises(ConnectionError, match="closed"):
            await client.request("session.ping")
        await client.close(abort=True)


@pytest.mark.asyncio
async def test_client_accepts_response_above_default_stream_limit() -> None:
    large_result = {"text": "x" * 70_000}

    def responses(request):
        result = _hello() if request["method"] == "session.hello" else large_result
        return {"jsonrpc": "2.0", "id": request["id"], "result": result}

    server, port = await _serve_once(responses)
    async with server:
        client = await PlayGodotClient.connect("127.0.0.1", port, token="x" * 32)
        assert await client.request("scene.tree") == large_result
        await client.close(abort=True)


@pytest.mark.asyncio
async def test_terminal_reader_error_rejects_future_requests_immediately() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hello = json.loads(await reader.readline())
        writer.write(
            json.dumps({"jsonrpc": "2.0", "id": hello["id"], "result": _hello()}).encode() + b"\n"
        )
        await writer.drain()
        await reader.readline()
        writer.write(b"invalid\n")
        await writer.drain()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        client = await PlayGodotClient.connect("127.0.0.1", port, token="x" * 32)
        with pytest.raises(ProtocolError, match="malformed JSON"):
            await client.request("scene.current")
        with pytest.raises(ProtocolError, match="malformed JSON"):
            await client.request("session.ping")
        await client.close(abort=True)


@pytest.mark.asyncio
async def test_oversized_response_is_a_protocol_error() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hello = json.loads(await reader.readline())
        writer.write(
            json.dumps({"jsonrpc": "2.0", "id": hello["id"], "result": _hello()}).encode() + b"\n"
        )
        await writer.drain()
        request = json.loads(await reader.readline())
        prefix = f'{{"jsonrpc":"2.0","id":{request["id"]},"result":"'
        writer.write(prefix.encode() + b"x" * 2_000_001 + b'"}\n')
        await writer.drain()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        client = await PlayGodotClient.connect("127.0.0.1", port, token="x" * 32)
        with pytest.raises(ProtocolError, match="exceeded"):
            await client.request("scene.tree")
        await client.close(abort=True)


@pytest.mark.asyncio
async def test_concurrent_requests_keep_distinct_ids_and_correlate_reversed_responses() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hello = json.loads(await reader.readline())
        writer.write(
            json.dumps({"jsonrpc": "2.0", "id": hello["id"], "result": _hello()}).encode() + b"\n"
        )
        await writer.drain()
        requests = [json.loads(await reader.readline()), json.loads(await reader.readline())]
        assert requests[0]["id"] != requests[1]["id"]
        for request in reversed(requests):
            writer.write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request["id"], "result": request["method"]}
                ).encode()
                + b"\n"
            )
        await writer.drain()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        client = await PlayGodotClient.connect("127.0.0.1", port, token="x" * 32)
        first, second = await asyncio.gather(
            client.request("scene.current"), client.request("session.ping")
        )
        assert (first, second) == ("scene.current", "session.ping")
        await client.close(abort=True)
