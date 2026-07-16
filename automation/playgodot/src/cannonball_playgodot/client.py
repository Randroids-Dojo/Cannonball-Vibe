from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "1.0"
MAX_REQUEST_BYTES = 65_536
MAX_RESPONSE_BYTES = 2_000_000
REQUIRED_LIMITS = {
    "request_bytes",
    "response_bytes",
    "json_depth",
    "tree_depth",
    "tree_nodes",
    "signal_wait_ms",
    "screenshot_bytes",
}


class ProtocolError(RuntimeError):
    """The peer violated the bounded PlayGodot wire contract."""


class PlayGodotError(RuntimeError):
    def __init__(self, code: int, name: str, message: str) -> None:
        super().__init__(f"{name} ({code}): {message}")
        self.code = code
        self.name = name
        self.message = message


class PlayGodotClient:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        timeout: float = 10.0,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._timeout = timeout
        self._next_id = 1
        self._send_lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._terminal_error: BaseException | None = None
        self._reader_task = asyncio.create_task(self._read_responses())

    @classmethod
    async def connect(
        cls,
        host: str,
        port: int,
        *,
        token: str,
        capabilities: tuple[str, ...] = ("read",),
        timeout: float = 10.0,
    ) -> PlayGodotClient:
        if host != "127.0.0.1":
            raise ValueError("PlayGodot clients only connect to IPv4 loopback")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, limit=MAX_RESPONSE_BYTES + 1), timeout
        )
        client = cls(reader, writer, timeout=timeout)
        try:
            hello = await client.request(
                "session.hello",
                {
                    "token": token,
                    "protocol": PROTOCOL_VERSION,
                    "capabilities": list(capabilities),
                },
            )
            client._validate_hello(hello, capabilities)
        except BaseException:
            await client.close(abort=True)
            raise
        return client

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._terminal_error is not None:
            raise self._terminal_error
        if self._writer.is_closing():
            raise ConnectionError("PlayGodot connection is closed")
        async with self._send_lock:
            request_id = self._next_id
            self._next_id += 1
            try:
                payload = json.dumps(
                    {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
                    separators=(",", ":"),
                ).encode()
            except (TypeError, ValueError) as error:
                raise ProtocolError(
                    "PlayGodot request parameters are not JSON serializable"
                ) from error
            if len(payload) > MAX_REQUEST_BYTES:
                raise ProtocolError("PlayGodot request exceeded the client byte limit")
            future = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future
            try:
                self._writer.write(payload + b"\n")
                await asyncio.wait_for(self._writer.drain(), self._timeout)
            except BaseException:
                self._pending.pop(request_id, None)
                future.cancel()
                self._writer.close()
                raise
        try:
            return await asyncio.wait_for(asyncio.shield(future), self._timeout)
        except TimeoutError as error:
            self._pending.pop(request_id, None)
            future.cancel()
            self._writer.close()
            raise TimeoutError(f"PlayGodot request timed out: {method}") from error
        except asyncio.CancelledError:
            self._pending.pop(request_id, None)
            future.cancel()
            self._writer.close()
            raise

    async def _read_responses(self) -> None:
        try:
            while True:
                try:
                    line = await self._reader.readline()
                except ValueError as error:
                    raise ProtocolError(
                        "PlayGodot response exceeded the client byte limit"
                    ) from error
                if not line:
                    raise ProtocolError("PlayGodot closed the connection without a response")
                response = self._decode_response(line)
                request_id = response["id"]
                future = self._pending.pop(request_id, None)
                if future is None:
                    raise ProtocolError("PlayGodot returned an unknown or duplicate response ID")
                if "error" in response:
                    detail = response["error"]
                    if not isinstance(detail, dict):
                        raise ProtocolError("PlayGodot returned an invalid error envelope")
                    future.set_exception(
                        PlayGodotError(
                            int(detail.get("code", -1)),
                            str(detail.get("name", "UNKNOWN")),
                            str(detail.get("message", "Unknown PlayGodot error")),
                        )
                    )
                else:
                    future.set_result(response["result"])
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            self._terminal_error = error
            self._writer.close()
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    @staticmethod
    def _decode_response(line: bytes) -> dict[str, Any]:
        if len(line) > MAX_RESPONSE_BYTES:
            raise ProtocolError("PlayGodot response exceeded the client byte limit")
        try:
            response = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProtocolError("PlayGodot returned malformed JSON") from error
        response_id = response.get("id") if isinstance(response, dict) else None
        has_result = isinstance(response, dict) and "result" in response
        has_error = isinstance(response, dict) and "error" in response
        if (
            not isinstance(response, dict)
            or response.get("jsonrpc") != "2.0"
            or not isinstance(response_id, int)
            or isinstance(response_id, bool)
            or response_id < 1
            or has_result == has_error
        ):
            raise ProtocolError("PlayGodot returned an invalid response envelope")
        if has_error:
            error = response["error"]
            if (
                not isinstance(error, dict)
                or not isinstance(error.get("code"), int)
                or isinstance(error.get("code"), bool)
                or not isinstance(error.get("name"), str)
                or not isinstance(error.get("message"), str)
            ):
                raise ProtocolError("PlayGodot returned an invalid error envelope")
        return response

    @staticmethod
    def _validate_hello(result: Any, requested: tuple[str, ...]) -> None:
        expected = list(dict.fromkeys(("read", *requested)))
        if not isinstance(result, dict):
            raise ProtocolError("PlayGodot returned an invalid handshake")
        limits = result.get("limits")
        if (
            result.get("protocol") != PROTOCOL_VERSION
            or result.get("engine") != "4.7.1-stable (official)"
            or result.get("build") != "debug"
            or result.get("capabilities") != expected
            or not isinstance(limits, dict)
            or not limits.keys() >= REQUIRED_LIMITS
            or any(
                not isinstance(limits[name], int | float)
                or isinstance(limits[name], bool)
                or limits[name] <= 0
                for name in REQUIRED_LIMITS
            )
        ):
            raise ProtocolError("PlayGodot returned an invalid handshake")

    async def describe(self, automation_id: str) -> dict[str, Any]:
        return await self.request("ui.describe", {"automation_id": automation_id})

    async def tree(self, *, max_depth: int = 8, max_nodes: int = 512) -> dict[str, Any]:
        return await self.request("scene.tree", {"max_depth": max_depth, "max_nodes": max_nodes})

    async def screenshot(
        self, destination: Path, *, automation_id: str | None = None
    ) -> dict[str, Any]:
        method = "screenshot.node" if automation_id else "screenshot.viewport"
        params = {"automation_id": automation_id} if automation_id else {}
        result = await self.request(method, params)
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("data"), str)
            or not isinstance(result.get("bytes"), int)
            or not isinstance(result.get("sha256"), str)
            or len(result["sha256"]) != 64
            or result.get("format") != "png"
            or not isinstance(result.get("width"), int | float)
            or not isinstance(result.get("height"), int | float)
        ):
            raise ProtocolError("PlayGodot returned invalid screenshot metadata")
        encoded = result.pop("data")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise ProtocolError("PlayGodot returned invalid screenshot data") from error
        if (
            len(content) != result["bytes"]
            or hashlib.sha256(content).hexdigest() != result["sha256"]
        ):
            raise ProtocolError("PlayGodot screenshot integrity check failed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return result

    async def close(self, *, abort: bool = False) -> None:
        if not self._writer.is_closing() and not abort:
            with contextlib.suppress(
                ConnectionError, OSError, PlayGodotError, ProtocolError, TimeoutError
            ):
                await self.request("session.close")
        self._reader_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._reader_task
        if not self._writer.is_closing():
            self._writer.close()
        close_error = ConnectionError("PlayGodot connection closed")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(close_error)
        self._pending.clear()
        with contextlib.suppress(ConnectionError, OSError):
            await self._writer.wait_closed()

    async def __aenter__(self) -> PlayGodotClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()
