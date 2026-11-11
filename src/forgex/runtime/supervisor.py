"""Subprocess supervision and lifecycle coordination for FORGEX."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from forgex.runtime.limits import ResourceLimits
from forgex.runtime.output import OutputSnapshot, ProcessOutputBuffer
from forgex.runtime.resource_manager import RuntimeResourceManager

logger = logging.getLogger(__name__)


class SupervisedProcessState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    TERMINATING = "terminating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class SupervisedProcessResult:
    process_id: str
    pid: int
    return_code: int
    state: SupervisedProcessState
    output: OutputSnapshot
    duration_seconds: float


@dataclass(slots=True)
class _ProcessEntry:
    process: asyncio.subprocess.Process
    state: SupervisedProcessState
    started_at: float
    output: ProcessOutputBuffer


class ProcessSupervisor:
    """Supervise asynchronous subprocesses with bounded output capture.

    Commands are executed directly using argv. Shell interpretation is
    deliberately not enabled by this supervisor.
    """

    def __init__(
        self,
        limits: ResourceLimits | None = None,
        resource_manager: RuntimeResourceManager | None = None,
        *,
        terminate_grace_period: float = 3.0,
        read_chunk_size: int = 8192,
    ) -> None:
        if terminate_grace_period < 0:
            raise ValueError("terminate_grace_period cannot be negative.")

        if read_chunk_size < 1:
            raise ValueError("read_chunk_size must be positive.")

        self.limits = limits or ResourceLimits()
        self.resources = resource_manager or RuntimeResourceManager(self.limits)
        self.terminate_grace_period = terminate_grace_period
        self.read_chunk_size = read_chunk_size

        self._processes: dict[str, _ProcessEntry] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def execute(
        self,
        argv: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> SupervisedProcessResult:
        """Launch and supervise a process until completion."""

        if self._closed:
            raise RuntimeError("Process supervisor is closed.")

        if not argv or not all(isinstance(arg, str) for arg in argv):
            raise ValueError("argv must contain non-empty string arguments.")

        if any("\x00" in arg for arg in argv):
            raise ValueError("Command arguments cannot contain null bytes.")

        working_directory = Path(cwd).expanduser().resolve()

        if not working_directory.is_dir():
            raise ValueError("Working directory does not exist.")

        execution_timeout = timeout or self.limits.timeout_seconds

        if execution_timeout <= 0:
            raise ValueError("timeout must be positive.")

        process_id = str(uuid.uuid4())
        started = time.monotonic()

        async with self.resources.process_slot():
            if self._closed:
                raise RuntimeError("Process supervisor is closed.")

            process = await self._spawn(
                argv,
                cwd=working_directory,
                env=env,
            )

            output = ProcessOutputBuffer(
                max_bytes_per_stream=self.limits.max_output_bytes // 2 or 1
            )

            entry = _ProcessEntry(
                process=process,
                state=SupervisedProcessState.RUNNING,
                started_at=started,
                output=output,
            )

            async with self._lock:
                self._processes[process_id] = entry

            try:
                await asyncio.wait_for(
                    self._collect_output(process, output),
                    timeout=execution_timeout,
                )

                return_code = await process.wait()

                state = (
                    SupervisedProcessState.COMPLETED
                    if return_code == 0
                    else SupervisedProcessState.FAILED
                )

                entry.state = state

                return SupervisedProcessResult(
                    process_id=process_id,
                    pid=process.pid,
                    return_code=return_code,
                    state=state,
                    output=output.snapshot(),
                    duration_seconds=time.monotonic() - started,
                )

            except TimeoutError:
                entry.state = SupervisedProcessState.TIMED_OUT
                await self._terminate(process)

                return SupervisedProcessResult(
                    process_id=process_id,
                    pid=process.pid,
                    return_code=process.returncode if process.returncode is not None else -1,
                    state=SupervisedProcessState.TIMED_OUT,
                    output=output.snapshot(),
                    duration_seconds=time.monotonic() - started,
                )

            except asyncio.CancelledError:
                entry.state = SupervisedProcessState.CANCELLED
                await self._terminate(process)
                raise

            except Exception:
                entry.state = SupervisedProcessState.FAILED
                await self._terminate(process)
                raise

            finally:
                async with self._lock:
                    self._processes.pop(process_id, None)

    async def _spawn(
        self,
        argv: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        env: Mapping[str, str] | None,
    ) -> asyncio.subprocess.Process:
        """Start a process in an isolated process group."""

        kwargs: dict[str, Any] = {
            "cwd": str(cwd),
            "env": dict(env) if env is not None else None,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }

        if os.name == "nt":
            kwargs["creationflags"] = getattr(
                __import__("subprocess"),
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )
        else:
            kwargs["start_new_session"] = True

        return await asyncio.create_subprocess_exec(*argv, **kwargs)

    async def _collect_output(
        self,
        process: asyncio.subprocess.Process,
        output: ProcessOutputBuffer,
    ) -> None:
        """Read stdout and stderr concurrently without deadlocking."""

        async def consume(
            reader: asyncio.StreamReader | None,
            stream: str,
        ) -> None:
            if reader is None:
                return

            while True:
                chunk = await reader.read(self.read_chunk_size)

                if not chunk:
                    break

                output.write(stream, chunk)

        await asyncio.gather(
            consume(process.stdout, "stdout"),
            consume(process.stderr, "stderr"),
        )

    async def _terminate(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        """Gracefully terminate a process group, then force-kill it."""

        if process.returncode is not None:
            return

        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)

        except ProcessLookupError:
            return

        except OSError:
            logger.exception("Graceful termination failed for PID %s.", process.pid)

        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=self.terminate_grace_period,
            )
            return
        except TimeoutError:
            pass

        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)

        except ProcessLookupError:
            pass

        except OSError:
            logger.exception("Force termination failed for PID %s.", process.pid)

        await process.wait()

    async def terminate(self, process_id: str) -> bool:
        """Terminate a currently supervised process."""

        async with self._lock:
            entry = self._processes.get(process_id)

            if entry is None:
                return False

            entry.state = SupervisedProcessState.TERMINATING

        await self._terminate(entry.process)
        return True

    async def active_processes(self) -> dict[str, int]:
        """Return active process IDs and operating-system PIDs."""

        async with self._lock:
            return {
                process_id: entry.process.pid
                for process_id, entry in self._processes.items()
                if entry.process.returncode is None
            }

    async def shutdown(self) -> None:
        """Stop accepting work and terminate active processes."""

        self._closed = True

        async with self._lock:
            entries = list(self._processes.values())

        await asyncio.gather(
            *(self._terminate(entry.process) for entry in entries),
            return_exceptions=True,
        )

    @property
    def is_closed(self) -> bool:
        return self._closed
