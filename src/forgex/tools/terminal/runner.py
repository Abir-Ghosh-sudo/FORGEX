
"""ProcessSupervisor-backed terminal runner for FORGEX."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from forgex.runtime.supervisor import ProcessSupervisor
from forgex.tools.terminal.models import (
    TerminalExecutionStatus,
    TerminalRequest,
    TerminalResult,
)

logger = logging.getLogger(__name__)


class TerminalRunnerError(Exception):
    """Raised when terminal execution cannot be started."""


class SupervisorTerminalRunner:
    """Execute terminal requests through the runtime supervisor.

    Commands are passed as argv directly. No shell interpolation is used.
    """

    def __init__(self, supervisor: ProcessSupervisor) -> None:
        if supervisor is None:
            raise ValueError("ProcessSupervisor is required.")

        self._supervisor = supervisor

    async def run(self, request: TerminalRequest) -> TerminalResult:
        """Execute a terminal request and normalize its result."""

        if not isinstance(request, TerminalRequest):
            raise TypeError("request must be a TerminalRequest.")

        started_at = time.monotonic()

        try:
            raw_result = await self._supervisor.execute(
                argv=request.argv,
                cwd=request.working_directory,
                timeout=request.timeout_seconds,
                env=dict(request.environment) or None,
            )

            duration = max(0.0, time.monotonic() - started_at)

            return self._convert_result(
                raw_result=raw_result,
                request=request,
                duration=duration,
            )

        except asyncio.CancelledError:
            logger.info(
                "Terminal process cancelled: executable=%s session=%s",
                request.executable,
                request.session_id,
            )
            raise

        except TimeoutError:
            return TerminalResult(
                status=TerminalExecutionStatus.TIMED_OUT,
                argv=request.argv,
                exit_code=None,
                stdout="",
                stderr="",
                duration_seconds=max(0.0, time.monotonic() - started_at),
                working_directory=request.working_directory,
                error="Terminal execution timed out.",
            )

        except Exception as exc:
            logger.exception(
                "Supervisor execution failed: executable=%s",
                request.executable,
            )
            raise TerminalRunnerError(
                f"Could not execute {request.executable!r}: {exc}"
            ) from exc

    @staticmethod
    def _convert_result(
        *,
        raw_result: object,
        request: TerminalRequest,
        duration: float,
    ) -> TerminalResult:
        """Convert the supervisor's result into the terminal API model."""

        exit_code = getattr(raw_result, "returncode", None)

        if exit_code is None:
            exit_code = getattr(raw_result, "exit_code", None)

        stdout = getattr(raw_result, "stdout", "")
        stderr = getattr(raw_result, "stderr", "")

        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")

        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")

        if not isinstance(stdout, str) or not isinstance(stderr, str):
            raise TerminalRunnerError(
                "Supervisor returned invalid stdout or stderr."
            )

        if exit_code is not None and not isinstance(exit_code, int):
            raise TerminalRunnerError(
                "Supervisor returned an invalid exit code."
            )

        if exit_code is None:
            status = TerminalExecutionStatus.FAILED
        elif exit_code == 0:
            status = TerminalExecutionStatus.SUCCESS
        else:
            status = TerminalExecutionStatus.FAILED

        truncated = bool(getattr(raw_result, "truncated", False))

        return TerminalResult(
            status=status,
            argv=request.argv,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            working_directory=request.working_directory,
            truncated=truncated,
            process_id=getattr(raw_result, "process_id", None),
            error=(
                None
                if status is TerminalExecutionStatus.SUCCESS
                else f"Process exited with code {exit_code}."
            ),
        )
