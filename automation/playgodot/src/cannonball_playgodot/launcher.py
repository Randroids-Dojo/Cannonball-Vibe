from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import secrets
import shutil
import signal
from collections import deque
from pathlib import Path

from .client import PlayGodotClient, ProtocolError

READY_PREFIX = "PLAYGODOT_READY "


class PlayGodotProcess:
    def __init__(
        self,
        repo_root: Path,
        route_package: Path,
        *,
        capabilities: tuple[str, ...] = ("read",),
        godot_bin: Path | None = None,
        startup_timeout: float = 20.0,
        transcript: Path | None = None,
        log_path: Path | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.route_package = route_package.resolve()
        self.capabilities = capabilities
        self.godot_bin = godot_bin or self._godot_from_environment()
        self.startup_timeout = startup_timeout
        self.transcript = transcript
        self.log_path = log_path
        self.process: asyncio.subprocess.Process | None = None
        self.client: PlayGodotClient | None = None
        self.output: deque[str] = deque(maxlen=1_000)
        self._drain_task: asyncio.Task[None] | None = None

    @staticmethod
    def _godot_from_environment() -> Path:
        value = os.environ.get("GODOT_BIN", "godot")
        resolved = shutil.which(value)
        if resolved:
            return Path(resolved)
        return Path(value)

    async def start(self) -> PlayGodotClient:
        if self.process is not None:
            raise RuntimeError("PlayGodot process is already running")
        if not self.godot_bin.is_file():
            raise FileNotFoundError(self.godot_bin)
        if not self.route_package.is_file():
            raise FileNotFoundError(self.route_package)
        token = secrets.token_urlsafe(32)
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text("")
        environment = os.environ.copy()
        environment["PLAYGODOT_TOKEN"] = token
        environment["PLAYGODOT_CAPABILITIES"] = ",".join(self.capabilities)
        if self.transcript is not None:
            self.transcript.parent.mkdir(parents=True, exist_ok=True)
            environment["PLAYGODOT_TRANSCRIPT"] = str(self.transcript.resolve())
        command = [
            str(self.godot_bin),
            "--audio-driver",
            "Dummy",
            "--rendering-method",
            "gl_compatibility",
            "--path",
            str(self.repo_root),
            "addons/playgodot/bootstrap.tscn",
            "--",
            "--playgodot",
            f"--route-package={self.route_package}",
        ]
        if platform.system() == "Linux" and os.environ.get("PLAYGODOT_XVFB") == "1":
            command = ["xvfb-run", "-a", *command]
        self.process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=environment,
            start_new_session=os.name == "posix",
        )
        try:
            ready = await asyncio.wait_for(self._read_ready(), self.startup_timeout)
            if ready.get("address") != "127.0.0.1" or ready.get("protocol") != "1.0":
                raise ProtocolError("PlayGodot advertised an unsafe or incompatible endpoint")
            if ready.get("engine") != "4.7.1-stable (official)":
                raise ProtocolError("PlayGodot did not start on official Godot 4.7.1")
            self._drain_task = asyncio.create_task(self._drain_output())
            self.client = await PlayGodotClient.connect(
                ready["address"], int(ready["port"]), token=token, capabilities=self.capabilities
            )
            return self.client
        except BaseException:
            await self.stop()
            raise

    async def _read_ready(self) -> dict[str, object]:
        assert self.process is not None and self.process.stdout is not None
        while True:
            line_bytes = await self.process.stdout.readline()
            if not line_bytes:
                exit_code = await self.process.wait()
                tail = "\n".join(list(self.output)[-20:])
                raise RuntimeError(f"Godot exited before PlayGodot was ready ({exit_code})\n{tail}")
            line = line_bytes.decode(errors="replace").rstrip()
            self._record_output(line)
            if line.startswith(READY_PREFIX):
                try:
                    ready = json.loads(line.removeprefix(READY_PREFIX))
                except json.JSONDecodeError as error:
                    raise ProtocolError("PlayGodot printed a malformed ready record") from error
                if not isinstance(ready, dict):
                    raise ProtocolError("PlayGodot printed an invalid ready record")
                return ready

    async def _drain_output(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while line_bytes := await self.process.stdout.readline():
            self._record_output(line_bytes.decode(errors="replace").rstrip())

    def _record_output(self, line: str) -> None:
        self.output.append(line)
        if self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8", newline="\n") as log:
                log.write(line + "\n")

    async def stop(self) -> None:
        cancellation: asyncio.CancelledError | None = None
        try:
            if self.client is not None:
                await self.client.close()
        except asyncio.CancelledError as error:
            cancellation = error
        except BaseException:
            pass
        finally:
            self.client = None
        cleanup = asyncio.create_task(self._stop_process())
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError as error:
            cancellation = error
            await cleanup
        if cancellation is not None:
            raise cancellation

    async def _stop_process(self) -> None:
        if self.process is None:
            return
        if self.process.returncode is None:
            self._signal_process(force=False)
            try:
                await asyncio.wait_for(self.process.wait(), 5.0)
            except TimeoutError:
                self._signal_process(force=True)
                await self.process.wait()
        if self._drain_task is not None:
            await self._drain_task
            self._drain_task = None
        self.process = None

    def _signal_process(self, *, force: bool) -> None:
        assert self.process is not None
        with contextlib.suppress(ProcessLookupError):
            if os.name == "posix":
                os.killpg(self.process.pid, signal.SIGKILL if force else signal.SIGTERM)
            elif force:
                self.process.kill()
            else:
                self.process.terminate()

    async def __aenter__(self) -> PlayGodotClient:
        return await self.start()

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()
