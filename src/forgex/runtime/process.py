
"""Asynchronous process execution and lifecycle management for FORGEX."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence

from forgex.runtime.adapters import RuntimeCommand


class ProcessStatus(StrEnum):
    """Lifecycle status of a managed process."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Immutable result of a completed process execution."""

    command: tuple[str, ...]
    return_code: int | None
    stdout: str
    stderr: str
    status: ProcessStatus
    duration_seconds: float

    @property
    def succeeded(self) -> bool:
        return self.status == ProcessStatus.COMPLETED and self.return_code == 0

    @property
    def failed(self) -> bool:
        return self.status == ProcessStatus.FAILED or (
            self.return_code is not None and self.return_code != 0
        )


@dataclass(frozen=True, slots=True)
class ProcessSpec:
    """Configuration for a process execution."""

    command: RuntimeCommand
    timeout_seconds: float | None = 300.0
    encoding: str = "utf-8"
    errors: str = "replace"
    max_output_bytes: int = 10 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("Process timeout must be positive.")

        if self.max_output_bytes <= 0:
            raise ValueError("Maximum output size must be positive.")

        if not self.encoding.strip():
            raise ValueError("Output encoding cannot be empty.")


class ProcessExecutionError(RuntimeError):
    """Raised when a process cannot be started or managed."""


class ProcessManager:
    """Manages asynchronous subprocess execution."""

    def __init__(self) -> None:
        self._processes: dict[int, asyncio.subprocess.Process] = {}
        self._statuses: dict[int, ProcessStatus] = {}
        self._lock = asyncio.Lock()

    async def execute(
        self,
        spec: ProcessSpec,
        *,
        input_text: str | None = None,
    ) -> ProcessResult:
        """Execute a command asynchronously and capture its output.

        Commands are executed directly through argv without a shell.
        Security authorization must be completed by the caller before
        invoking this method.
        """

        command = spec.command
        argv = command.argv

        started = time.monotonic()
        process: asyncio.subprocess.Process | None = None

        try:
            kwargs: dict[str, object] = {
                "cwd": str(command.working_directory),
                "env": command.environment,
                "stdin": (
                    asyncio.subprocess.PIPE
                    if input_text is not None
                    else asyncio.subprocess.DEVNULL
                ),
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            }

            if os.name != "nt":
                kwargs["start_new_session"] = True
            else:
                kwargs["creationflags"] = getattr(
                    __import__("subprocess"),
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                )

            process = await asyncio.create_subprocess_exec(
                *argv,
                **kwargs,
            )

            pid = process.pid

            async with self._lock:
                self._processes[pid] = process
                self._statuses[pid] = ProcessStatus.RUNNING

            input_bytes = (
                input_text.encode(spec.encoding)
                if input_text is not None
                else None
            )

            try:
                if spec.timeout_seconds is None:
                    stdout_bytes, stderr_bytes = await process.communicate(
                        input_bytes
                    )
                else:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        process.communicate(input_bytes),
                        timeout=spec.timeout_seconds,
                    )

            except TimeoutError:
                await self._terminate_process(process)

                async with self._lock:
                    self._statuses[pid] = ProcessStatus.TIMED_OUT

                stdout_bytes, stderr_bytes = await process.communicate()

                return self._build_result(
                    spec,
                    process,
                    stdout_bytes,
                    stderr_bytes,
                    ProcessStatus.TIMED_OUT,
                    started,
                )

            status = (
                ProcessStatus.COMPLETED
                if process.returncode == 0
                else ProcessStatus.FAILED
            )

            async with self._lock:
                self._statuses[pid] = status

            return self._build_result(
                spec,
                process,
                stdout_bytes,
                stderr_bytes,
                status,
                started,
            )

        except asyncio.CancelledError:
            if process is not None and process.returncode is None:
                await self._terminate_process(process)

                async with self._lock:
                    self._statuses[process.pid] = ProcessStatus.CANCELLED

            raise

        except (OSError, ValueError) as exc:
            raise ProcessExecutionError(
                f"Could not execute process: {exc}"
            ) from exc

        finally:
            if process is not None:
                async with self._lock:
                    self._processes.pop(process.pid, None)

    async def terminate(
        self,
        pid: int,
        *,
        force: bool = False,
    ) -> bool:
        """Terminate a managed process by PID."""

        async with self._lock:
            process = self._processes.get(pid)

        if process is None or process.returncode is not None:
            return False

        try:
            if force:
                await self._kill_process(process)
            else:
                await self._terminate_process(process)

            async with self._lock:
                self._statuses[pid] = ProcessStatus.TERMINATED

            return True

        except ProcessLookupError:
            return False

    async def terminate_all(self, *, force: bool = False) -> int:
        """Terminate every currently managed process."""

        async with self._lock:
            pids = list(self._processes)

        terminated = 0

        for pid in pids:
            if await self.terminate(pid, force=force):
                terminated += 1

        return terminated

    async def get_status(self, pid: int) -> ProcessStatus | None:
        """Get the current or last recorded process status."""

        async with self._lock:
            return self._statuses.get(pid)

    async def active_processes(self) -> list[int]:
        """Return PIDs of currently managed processes."""

        async with self._lock:
            return [
                pid
                for pid, process in self._processes.items()
                if process.returncode is None
            ]

    async def _terminate_process(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        """Gracefully terminate a process, escalating after a short delay."""

        if process.returncode is not None:
            return

        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except TimeoutError:
            await self._kill_process(process)

    async def _kill_process(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        """Forcefully terminate a process."""

        if process.returncode is not None:
            return

        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return

        await process.wait()

    @staticmethod
    def _build_result(
        spec: ProcessSpec,
        process: asyncio.subprocess.Process,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        status: ProcessStatus,
        started: float,
    ) -> ProcessResult:
        """Build a bounded and decoded process result."""

        limit = spec.max_output_bytes

        stdout = stdout_bytes[:limit].decode(
            spec.encoding,
            errors=spec.errors,
        )
        stderr = stderr_bytes[:limit].decode(
            spec.encoding,
            errors=spec.errors,
        )

        if len(stdout_bytes) > limit:
            stdout += "\n[FORGEX: stdout truncated]"

        if len(stderr_bytes) > limit:
            stderr += "\n[FORGEX: stderr truncated]"

        return ProcessResult(
            command=tuple(spec.command.argv),
            return_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            status=status,
            duration_seconds=max(0.0, time.monotonic() - started),
        )
