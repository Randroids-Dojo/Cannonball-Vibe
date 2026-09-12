from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import math
import os
import platform
import re
import secrets
import shutil
import signal
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

from .client import PlayGodotClient, PlayGodotError, ProtocolError

READY_PREFIX = "PLAYGODOT_READY "
VEHICLE_RENDER_PREFIX = "PLAYGODOT_VEHICLE_RENDERED "
VEHICLE_RENDER_FAILURE_PREFIX = "PLAYGODOT_VEHICLE_RENDER_FAILED "
MAX_VEHICLE_RENDER_RECORDS = 64
QUIT_PREFIX = "PLAYGODOT_QUIT "
SHUTDOWN_PHASE_SECONDS = (5.0, 1.0, 1.0, 1.0)
SHUTDOWN_TIMEOUT_SECONDS = sum(SHUTDOWN_PHASE_SECONDS)
_EXIT_DIAGNOSTIC = re.compile(
    r"Unreferenced static string|PagedAllocator|ObjectDB.*leak|RID.*leak|"
    r"Thread object.*destroy|libc\+\+abi:|uncaught exception|fatal|crash|mutex.*failed",
    re.IGNORECASE,
)


class ShutdownError(RuntimeError):
    """The owned native process did not prove a clean, bounded exit."""


class PlayGodotProcess:
    def __init__(
        self,
        repo_root: Path,
        route_package: Path,
        *,
        capabilities: tuple[str, ...] = ("read",),
        godot_bin: Path | None = None,
        startup_timeout: float = 20.0,
        request_timeout: float = 10.0,
        transcript: Path | None = None,
        log_path: Path | None = None,
        production_vehicle: bool = False,
        vehicle: str | None = None,
        isolate_user_data: bool = False,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.route_package = route_package.resolve()
        self.capabilities = capabilities
        self.production_vehicle = production_vehicle
        if vehicle not in (None, "hero-gt", "endurance-sedan", "graybox"):
            raise ValueError("Unknown explicit PlayGodot vehicle")
        self.vehicle = vehicle
        self.isolate_user_data = isolate_user_data
        self.godot_bin = godot_bin or self._godot_from_environment()
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self.transcript = transcript
        self.log_path = log_path
        self.process: asyncio.subprocess.Process | None = None
        self.client: PlayGodotClient | None = None
        self.output: deque[str] = deque(maxlen=1_000)
        self._drain_task: asyncio.Task[None] | None = None
        self._runtime_directory: Path | None = None
        self.startup_elapsed_seconds: float | None = None
        self._vehicle_renders: deque[dict[str, object]] = deque(maxlen=MAX_VEHICLE_RENDER_RECORDS)
        self._vehicle_render_event = asyncio.Event()
        self._vehicle_render_error: Exception | None = None
        self._output_eof = False
        self._stopping = False
        self._shutdown_token: str | None = None
        self._shutdown_endpoint: tuple[str, int] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._cleanup_waits: set[asyncio.Task] = set()
        self._bookkeeping_future: asyncio.Future[dict[str, object]] | None = None
        self._shutdown_log_lines: list[str] = []
        self._output_lines = 0
        self._diagnostics: list[dict[str, object]] = []
        self._quit_record: dict[str, int] | None = None
        self._quit_accepted = False
        self.teardown_result: dict[str, object] | None = None

    @property
    def rendered_vehicle_generation(self) -> int:
        return int(self._vehicle_renders[-1]["generation"]) if self._vehicle_renders else 0

    async def wait_for_vehicle_render(
        self, asset_id: str, *, after_generation: int, timeout: float = 60.0,
    ) -> dict[str, object]:
        """Wait for a new body's completed draw, separately from live RPC deadlines."""
        if asset_id not in ("endurance-sedan", "hero-gt", "graybox"):
            raise ValueError("Unknown rendered vehicle")
        if (type(after_generation) is not int
                or not 0 <= after_generation <= self.rendered_vehicle_generation):
            raise ValueError("Render generation must be a captured current or prior generation")
        if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or not math.isfinite(timeout) or not 0 < timeout <= 60):
            raise ValueError("Render preparation must have a positive bound at most 60 seconds")
        started = asyncio.get_running_loop().time()
        deadline = started + timeout
        while True:
            self._vehicle_render_event.clear()
            if self._vehicle_render_error is not None:
                raise ProtocolError(
                    f"Invalid vehicle render preparation: {self._vehicle_render_error}"
                )
            if self._stopping or self._output_eof:
                raise RuntimeError("Godot stopped or closed stdout before vehicle render completed")
            for record in self._vehicle_renders:
                if int(record["generation"]) > after_generation and record["asset_id"] == asset_id:
                    return {
                        **record,
                        "preparation_budget_seconds": timeout,
                        "wait_elapsed_seconds": asyncio.get_running_loop().time() - started,
                    }
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(self._vehicle_render_event.wait(), remaining)
            except TimeoutError:
                break
        tail = "\n".join(list(self.output)[-20:])
        raise TimeoutError(
            f"Godot did not complete a new {asset_id} draw after generation {after_generation} "
            f"within the separate {timeout:g}s render preparation; process output:\n{tail}"
        )

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
        if ((self._cleanup_task is not None and not self._cleanup_task.done())
                or (self._drain_task is not None and not self._drain_task.done())
                or (self._bookkeeping_future is not None and not self._bookkeeping_future.done())
                or any(not task.done() for task in self._cleanup_waits)):
            raise RuntimeError("Previous PlayGodot cleanup is still incomplete")
        if not self.godot_bin.is_file():
            raise FileNotFoundError(self.godot_bin)
        if not self.route_package.is_file():
            raise FileNotFoundError(self.route_package)
        self._vehicle_renders.clear()
        self._vehicle_render_error = None
        self._vehicle_render_event.clear()
        self._output_eof = False
        self._drain_task = None
        self.output.clear()
        self._stopping = False
        self._cleanup_task = None
        self._bookkeeping_future = None
        self._shutdown_log_lines.clear()
        self.teardown_result = None
        self._shutdown_endpoint = None
        self._output_lines = 0
        self._diagnostics.clear()
        self._quit_record = None
        self._quit_accepted = False
        token = secrets.token_urlsafe(32)
        self._shutdown_token = token
        if self.log_path is None:
            descriptor, name = tempfile.mkstemp(prefix="cannonball-playgodot-", suffix=".log")
            os.close(descriptor)
            self.log_path = Path(name)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")
        environment = os.environ.copy()
        environment["PLAYGODOT_TOKEN"] = token
        environment["PLAYGODOT_CAPABILITIES"] = ",".join(
            dict.fromkeys((*self.capabilities, "shutdown"))
        )
        if self.transcript is not None:
            self.transcript.parent.mkdir(parents=True, exist_ok=True)
            environment["PLAYGODOT_TRANSCRIPT"] = str(self.transcript.resolve())
        self._runtime_directory = Path(
            tempfile.mkdtemp(prefix="cannonball-playgodot-")
        ).resolve()
        if self.isolate_user_data:
            # The selection test writes presentation settings. Scope its whole
            # child-process user profile, never the developer's real save/config.
            environment.update(
                HOME=str(self._runtime_directory),
                XDG_DATA_HOME=str(self._runtime_directory / "xdg-data"),
                APPDATA=str(self._runtime_directory / "appdata"),
                LOCALAPPDATA=str(self._runtime_directory / "localappdata"),
            )
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
            # The semantic suite runs the graybox environment: its assertions
            # are about input, camera, menu and restart behaviour, and the
            # software-rendered runners cannot draw the production art fast
            # enough to hold the suite's wall-clock bounds (Q-042).
            "--graybox-environment-assets",
            f"--route-package={self.route_package}",
            f"--telemetry-path={self._runtime_directory / 'telemetry.jsonl'}",
        ]
        if self.vehicle is not None:
            command.append(f"--vehicle={self.vehicle}")
        elif self.production_vehicle:
            # Legacy camera/visual tests exercise Hero's declared contract,
            # independent of a player's persisted sedan or graybox selection.
            command.append("--vehicle=hero-gt")
        else:
            # The same reasoning covers the car: the third-generation Hero GT
            # brought twenty-eight textured materials whose first draw stalls
            # the main thread for tens of seconds on the software renderers,
            # which is longer than the suite's request and settle windows.
            # Only the camera test needs the production rig's contract.
            command.append("--graybox-vehicle")
            command.append("--vehicle=graybox")
        if platform.system() == "Linux" and os.environ.get("PLAYGODOT_XVFB") == "1":
            command = ["xvfb-run", "-a", *command]
        try:
            startup_started = asyncio.get_running_loop().time()
            self.process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=environment,
                start_new_session=os.name == "posix",
            )
            try:
                ready = await asyncio.wait_for(self._read_ready(), self.startup_timeout)
            except TimeoutError as error:
                tail = "\n".join(list(self.output)[-20:])
                raise TimeoutError(
                    f"Godot did not advertise PLAYGODOT_READY within "
                    f"{self.startup_timeout:g}s; process output:\n{tail}"
                ) from error
            self.startup_elapsed_seconds = asyncio.get_running_loop().time() - startup_started
            if ready.get("address") != "127.0.0.1" or ready.get("protocol") != "1.0":
                raise ProtocolError("PlayGodot advertised an unsafe or incompatible endpoint")
            if ready.get("engine") != "4.7.1-stable (official)":
                raise ProtocolError("PlayGodot did not start on official Godot 4.7.1")
            if type(ready.get("port")) is not int or not 1 <= ready["port"] <= 65_535:
                raise ProtocolError("PlayGodot advertised an invalid endpoint port")
            self._shutdown_endpoint = ("127.0.0.1", ready["port"])
            self._drain_task = asyncio.create_task(self._drain_output())
            self.client = await PlayGodotClient.connect(
                ready["address"],
                int(ready["port"]),
                token=token,
                capabilities=self.capabilities,
                timeout=self.request_timeout,
            )
            return self.client
        except BaseException as original:
            await self._stop_preserving(original)
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
        try:
            while line_bytes := await self.process.stdout.readline():
                self._record_output(line_bytes.decode(errors="replace").rstrip())
                if self._output_lines % 32 == 0:
                    await asyncio.sleep(0)
            self._output_eof = True
        except Exception as error:
            self._vehicle_render_error = error
            raise
        finally:
            self._vehicle_render_event.set()

    def _record_output(self, line: str) -> None:
        self._output_lines += 1
        self.output.append(line)
        if line == "PLAYGODOT_QUIT_ACCEPTED":
            self._quit_accepted = True
        stripped = line.lstrip()
        exit_diagnostic = bool(_EXIT_DIAGNOSTIC.search(stripped))
        if exit_diagnostic or stripped.startswith(("ERROR:", "SCRIPT ERROR:")):
            self._diagnostics.append({
                "line": self._output_lines, "text": line,
                "shutdown": self._stopping or self._quit_accepted or exit_diagnostic,
            })
        if self.log_path is not None:
            if self._stopping or self._quit_accepted:
                # Shutdown pipe draining must not perform blocking disk I/O.
                # The bounded bookkeeping worker flushes these lines before
                # hashing the complete native log and writing observations.
                self._shutdown_log_lines.append(line)
            else:
                with self.log_path.open("a", encoding="utf-8", newline="\n") as log:
                    log.write(line + "\n")
        if line.startswith(QUIT_PREFIX):
            try:
                record = json.loads(line.removeprefix(QUIT_PREFIX))
                expected = {"pending_waits_before", "held_inputs_before",
                            "pending_waits_after", "held_inputs_after"}
                if (not isinstance(record, dict) or set(record) != expected
                        or any(type(value) is not int or value < 0 for value in record.values())
                        or record["pending_waits_after"] != 0 or record["held_inputs_after"] != 0):
                    raise ValueError("Invalid quit cleanup inventory")
                self._quit_record = record
                self._quit_accepted = True
            except (ValueError, TypeError):
                self._diagnostics.append({"line": self._output_lines,
                    "text": "Invalid PLAYGODOT_QUIT record", "shutdown": True})
        if line.startswith(VEHICLE_RENDER_PREFIX):
            try:
                self._record_vehicle_render(line.removeprefix(VEHICLE_RENDER_PREFIX))
            except (ValueError, TypeError) as error:
                self._vehicle_render_error = error
            self._vehicle_render_event.set()
        elif line.startswith(VEHICLE_RENDER_FAILURE_PREFIX):
            self._vehicle_render_error = ValueError(line)
            self._vehicle_render_event.set()

    def _record_vehicle_render(self, payload: str) -> None:
        if len(payload) > 4_096:
            raise ValueError("Vehicle render record exceeds its size bound")
        record = json.loads(payload)
        identifiers = (
            "vehicle_instance_id", "panel_instance_id",
            "viewport_instance_id", "camera_instance_id",
        )
        frame_kinds = ("process_frame", "physics_frame", "drawn_frame")
        integers = (*identifiers, "generation", "pre_draw_usec", "post_draw_usec",
                    *(f"{phase}_{kind}" for phase in ("pre", "post") for kind in frame_kinds))
        if not isinstance(record, dict) or set(record) != {"asset_id", *integers}:
            raise ValueError("Vehicle render record has an invalid field inventory")
        if record["asset_id"] not in ("endurance-sedan", "hero-gt", "graybox"):
            raise ValueError("Vehicle render record names an unknown asset")
        if any(type(record[key]) is not int or not 0 <= record[key] < 2**63 for key in integers):
            raise ValueError("Vehicle render record has an invalid integer field")
        if any(record[key] == 0 for key in identifiers):
            raise ValueError("Vehicle render record has an invalid instance identity")
        if (record["generation"] != self.rendered_vehicle_generation + 1
                or record["generation"] > MAX_VEHICLE_RENDER_RECORDS):
            raise ValueError("Vehicle render generation is repeated, skipped or out of bounds")
        if any(record[key] == prior[key] for prior in self._vehicle_renders
               for key in ("vehicle_instance_id", "panel_instance_id")):
            raise ValueError("Vehicle render record reused a previous body or panel instance")
        if record["post_draw_usec"] < record["pre_draw_usec"] or any(
            record[f"pre_{kind}"] != record[f"post_{kind}"] for kind in frame_kinds
        ):
            raise ValueError("Vehicle render record does not describe one ordered draw")
        self._vehicle_renders.append(record)

    async def stop(self) -> None:
        self._stopping = True
        self._vehicle_render_event.set()
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._stop_process())
        cancellation: asyncio.CancelledError | None = None
        while not self._cleanup_task.done():
            try:
                await asyncio.shield(self._cleanup_task)
            except asyncio.CancelledError as error:
                cancellation = cancellation or error
            except Exception:
                break
        try:
            self._cleanup_task.result()
        except BaseException as error:
            if cancellation is None:
                raise
            cancellation.add_note(f"Owned process cleanup also failed: {type(error).__name__}")
        if cancellation is not None:
            raise cancellation

    async def _stop_preserving(self, original: BaseException | None) -> None:
        try:
            await self.stop()
        except BaseException as cleanup_error:
            if original is None:
                raise
            original.add_note(
                f"Owned process cleanup also failed: {type(cleanup_error).__name__}; "
                f"native log: {self.log_path}; teardown result: {self.teardown_result}"
            )

    async def _before(self, awaitable, deadline: float):
        """A phase timeout must not await an uncooperative cancellation handler."""
        task = asyncio.ensure_future(awaitable)
        self._cleanup_waits.add(task)

        def completed(done: asyncio.Task) -> None:
            self._cleanup_waits.discard(done)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(completed)
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        done, _pending = await asyncio.wait((task,), timeout=remaining)
        if not done:
            task.cancel()
            raise TimeoutError("Owned process cleanup phase deadline expired")
        return task.result()

    @staticmethod
    def _abort_client(client: PlayGodotClient | None) -> None:
        if client is not None:
            client._writer.transport.abort()

    async def _request_quit(self, deadline: float, record: dict[str, object]) -> None:
        if self._shutdown_endpoint is None or self._shutdown_token is None:
            raise RuntimeError("No verified owned endpoint is available")
        owner: PlayGodotClient | None = None
        loop = asyncio.get_running_loop()
        while loop.time() < deadline:
            try:
                owner = await self._before(PlayGodotClient.connect(
                    *self._shutdown_endpoint, token=self._shutdown_token,
                    capabilities=("shutdown",), timeout=deadline - loop.time(),
                ), deadline)
                break
            except (ProtocolError, PlayGodotError, ConnectionResetError) as error:
                stale = (isinstance(error, ProtocolError)
                         and str(error) == "PlayGodot closed the connection without a response")
                stale = stale or isinstance(error, ConnectionResetError)
                stale = stale or (isinstance(error, PlayGodotError) and error.name == "BUSY")
                if not stale:
                    raise
                record["connection_turnover_retries"] += 1
                await self._before(asyncio.sleep(.02), deadline)
        if owner is None:
            raise TimeoutError("Owned quit handshake deadline expired")
        try:
            record["quit_requested"] = True
            response = await self._before(owner.request("session.quit"), deadline)
            if response != {"quitting": True} or type(response["quitting"]) is not bool:
                raise ProtocolError("Invalid owned quit acknowledgement")
            record["quit_acknowledged"] = True
        finally:
            self._abort_client(owner)
            # Abort performs no RPC and releases client reader/pending resources.
            await self._before(owner.close(abort=True), deadline)

    def _start_bookkeeping(self, record: dict[str, object]) -> asyncio.Future:
        """A stalled filesystem must not hold the owner or asyncio executor open.

        The daemon writes observations only. A late write cannot certify owner
        success; that requires the caller's successful return within its budget.
        Keep the completion future so a new launch cannot race an unfinished write.
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._bookkeeping_future = future
        snapshot = copy.deepcopy(record)
        snapshot["status"] = "native-observation"
        snapshot["owner_finalization_required"] = True
        profile = self._runtime_directory if self.process is None else None
        log_path = self.log_path
        shutdown_lines = tuple(self._shutdown_log_lines)

        def completed(result, error) -> None:
            if not future.done():
                if error is None:
                    future.set_result(result)
                else:
                    future.set_exception(error)
                    # Preserve the exception for an active waiter without an
                    # unobserved-future warning after a timed-out caller exits.
                    future.exception()

        def work() -> None:
            result, error = None, None
            try:
                result = {"profile_removed": False}
                if log_path is not None:
                    with log_path.open("a", encoding="utf-8", newline="\n") as log:
                        for line in shutdown_lines:
                            log.write(line + "\n")
                    data = log_path.read_bytes()
                    snapshot["native_log"] = {
                        "path": str(log_path), "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                    result["native_log"] = snapshot["native_log"]
                if profile is not None:
                    shutil.rmtree(profile)
                    result["profile_removed"] = True
                if log_path is not None:
                    snapshot["observation_write_started_seconds"] = (
                        time.monotonic() - record["started_monotonic_seconds"]
                    )
                    log_path.with_suffix(".shutdown.json").write_text(
                        json.dumps(snapshot, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8", newline="\n",
                    )
            except BaseException as caught:
                error = caught
            with contextlib.suppress(RuntimeError):  # The owner loop may already be closed.
                loop.call_soon_threadsafe(completed, result, error)

        threading.Thread(target=work, name="playgodot-bookkeeping", daemon=True).start()
        return future

    async def _stop_process(self) -> None:
        if self.process is None:
            if self._runtime_directory is not None:
                started = asyncio.get_running_loop().time()
                record = {"status": "not-started", "pid": None, "exit_status": None,
                          "started_monotonic_seconds": started}
                self.teardown_result = record
                try:
                    await self._before(asyncio.shield(self._start_bookkeeping(record)), started + 1)
                    self._runtime_directory = None
                except Exception as error:
                    record["status"] = "failed"
                    raise ShutdownError("Unstarted process profile cleanup failed") from error
            return
        loop = asyncio.get_running_loop()
        started = loop.time()
        normal_end = started + SHUTDOWN_PHASE_SECONDS[0]
        record: dict[str, object] = {
            "schema_version": 1, "pid": self.process.pid,
            "started_monotonic_seconds": started,
            "total_budget_seconds": SHUTDOWN_TIMEOUT_SECONDS,
            "phase_seconds": list(SHUTDOWN_PHASE_SECONDS), "quit_requested": False,
            "quit_acknowledged": False, "connection_turnover_retries": 0,
            "fallback": [], "phase_errors": [], "phase_events": [],
            "exit_status": None, "output_eof": False, "status": "failed",
        }
        self.teardown_result = record
        if self._drain_task is None:
            self._drain_task = asyncio.create_task(self._drain_output())

        def failed(phase: str, error: BaseException) -> None:
            # Remote/exception messages may contain caller data. Do not persist tokens.
            record["phase_errors"].append({"phase": phase, "type": type(error).__name__})

        if self.client is not None:
            try:
                await self._before(self.client.close(), min(normal_end, started + 1.0))
            except Exception as error:
                failed("session-close", error)
            finally:
                self._abort_client(self.client)
                self.client = None
        if self.process.returncode is None:
            try:
                await self._request_quit(normal_end, record)
            except Exception as error:
                failed("session-quit", error)
            try:
                await self._before(self.process.wait(), normal_end)
            except Exception as error:
                failed("graceful-exit", error)
        record["phase_events"].append({
            "phase": "graceful", "elapsed_seconds": loop.time() - started,
        })
        for index, force in ((1, False), (2, True)):
            if self.process.returncode is not None:
                break
            phase = "kill" if force else "terminate"
            record["fallback"].append(phase)
            try:
                self._signal_process(force=force)
                await self._before(self.process.wait(), min(
                    started + sum(SHUTDOWN_PHASE_SECONDS[:index + 1]),
                    loop.time() + SHUTDOWN_PHASE_SECONDS[index],
                ))
            except Exception as error:
                failed(phase, error)
            record["phase_events"].append({"phase": phase,
                                            "elapsed_seconds": loop.time() - started})
        final_end = min(started + SHUTDOWN_TIMEOUT_SECONDS,
                        loop.time() + SHUTDOWN_PHASE_SECONDS[3])
        try:
            await self._before(
                asyncio.shield(self._drain_task), final_end,
            )
        except Exception as error:
            failed("output-drain", error)
            self._drain_task.cancel()
        record.update(
            exit_status=self.process.returncode, output_eof=self._output_eof,
            quit_cleanup=self._quit_record, diagnostics=list(self._diagnostics),
        )
        if self.process.returncode is not None:
            self.process = None
            self._shutdown_token = None
        record["elapsed_seconds"] = loop.time() - started
        record["bookkeeping_completed"] = False
        try:
            bookkeeping = self._start_bookkeeping(record)
            if loop.time() >= final_end:
                raise TimeoutError("No bookkeeping budget remains")
            completed = await self._before(
                asyncio.shield(bookkeeping), final_end,
            )
            record["bookkeeping_completed"] = True
            if completed["profile_removed"]:
                self._runtime_directory = None
            if "native_log" in completed:
                record["native_log"] = completed["native_log"]
        except Exception as error:
            failed("bookkeeping", error)
        record["unfinished_operations"] = sum(not task.done() for task in self._cleanup_waits)
        record["elapsed_seconds"] = loop.time() - started
        record["status"] = "passed" if (
            record["exit_status"] == 0 and not record["fallback"]
            and self._output_eof and self._drain_task.done() and not self._drain_task.cancelled()
            and self._drain_task.exception() is None and self._quit_record is not None
            and not any(row["shutdown"] for row in self._diagnostics)
            and record["unfinished_operations"] == 0
            and record["bookkeeping_completed"]
            and not any(row["phase"] in ("output-drain", "bookkeeping")
                        for row in record["phase_errors"])
            and record["elapsed_seconds"] <= SHUTDOWN_TIMEOUT_SECONDS
        ) else "failed"
        if record["status"] != "passed":
            raise ShutdownError(
                f"Owned Godot cleanup failed (pid={record['pid']}, exit={record['exit_status']}, "
                f"fallback={record['fallback']}, phases={record['phase_errors']}); "
                f"native log: {self.log_path}"
            )

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

    async def __aexit__(self, _type, original: BaseException | None, _traceback) -> None:
        await self._stop_preserving(original)
