
"""Runtime supervisor adapter for FORGEX terminal execution."""

from __future__ import annotations

import inspect
import logging
from typing import Any

from forgex.runtime.supervisor import (
    ProcessSupervisor,
    SupervisedProcessResult,
    SupervisedProcessState,
)
from forgex.tools.terminal.models import (
    TerminalExecutionStatus,
    TerminalRequest,
    TerminalResult,
)

logger = logging.getLogger(__name__)


class TerminalRunnerError(Exception):
    """Raised when terminal execution or result conversion fails."""


class SupervisorTerminalRunner:
    """Execute terminal requests through the runtime ProcessSupervisor."""

    def __init__(self, supervisor: ProcessSupervisor) -> None:
        if not isinstance(supervisor, ProcessSupervisor):
            raise TypeError(
                "supervisor must be a ProcessSupervisor instance."
            )

        self._supervisor = supervisor

    async def run(self, request: TerminalRequest) -> TerminalResult:
        """Execute a validated terminal request."""

        if not isinstance(request, TerminalRequest):
            raise TypeError("request must be a TerminalRequest.")

        if request.stdin is not None:
            raise TerminalRunnerError(
                "The current ProcessSupervisor does not support stdin. "
                "Interactive input is unavailable."
            )

        try:
            raw_result = self._supervisor.execute(
                list(request.argv),
                cwd=request.working_directory,
                env=dict(request.environment) or None,
                timeout=request.timeout_seconds,
            )

            if inspect.isawaitable(raw_result):
                raw_result = await raw_result

            if not isinstance(raw_result, SupervisedProcessResult):
                raise TerminalRunnerError(
                    "ProcessSupervisor returned an invalid result."
                )

            return self._convert_result(request, raw_result)

        except TerminalRunnerError:
            raise

        except TimeoutError:
            logger.warning(
                "Terminal execution timed out: command=%s",
                request.argv[0],
            )
            return self._make_result(
                request,
                status=TerminalExecutionStatus.TIMED_OUT,
                exit_code=-1,
                error="Process execution timed out.",
            )

        except Exception as exc:
            logger.exception(
                "Terminal execution failed: command=%s",
                request.argv[0] if request.argv else "<empty>",
            )
            raise TerminalRunnerError(
                "Terminal process execution failed."
            ) from exc

    def _convert_result(
        self,
        request: TerminalRequest,
        result: SupervisedProcessResult,
    ) -> TerminalResult:
        """Convert runtime output into the terminal result model."""

        stdout, stderr, already_truncated = self._extract_output(
            result.output
        )

        stdout, stderr, truncated = self._apply_output_limit(
            stdout,
            stderr,
            request.max_output_bytes,
        )

        truncated = truncated or already_truncated

        state = result.state

        if state == SupervisedProcessState.TIMED_OUT:
            status = TerminalExecutionStatus.TIMED_OUT
            error = "Process execution timed out."
        elif state == SupervisedProcessState.CANCELLED:
            status = TerminalExecutionStatus.CANCELLED
            error = "Process execution was cancelled."
        elif state == SupervisedProcessState.COMPLETED:
            status = TerminalExecutionStatus.SUCCESS
            error = None
        else:
            status = TerminalExecutionStatus.FAILED
            error = f"Process exited with code {result.return_code}."

        return TerminalResult(
            status=status,
            argv=tuple(request.argv),
            exit_code=result.return_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=result.duration_seconds,
            working_directory=request.working_directory,
            truncated=truncated,
            process_id=str(result.process_id),
            error=error,
        )

    @staticmethod
    def _extract_output(snapshot: Any) -> tuple[str, str, bool]:
        """Extract stdout/stderr from an OutputSnapshot."""

        if snapshot is None:
            raise TerminalRunnerError(
                "ProcessSupervisor returned no output snapshot."
            )

        stdout = getattr(snapshot, "stdout", b"")
        stderr = getattr(snapshot, "stderr", b"")

        stdout_text = SupervisorTerminalRunner._decode(stdout)
        stderr_text = SupervisorTerminalRunner._decode(stderr)

        truncated = bool(
            getattr(snapshot, "truncated", False)
            or getattr(snapshot, "stdout_truncated", False)
            or getattr(snapshot, "stderr_truncated", False)
        )

        return stdout_text, stderr_text, truncated

    @staticmethod
    def _decode(value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")

        raise TerminalRunnerError(
            "Process output must be bytes, string, or None."
        )

    @staticmethod
    def _apply_output_limit(
        stdout: str,
        stderr: str,
        max_bytes: int,
    ) -> tuple[str, str, bool]:
        """Apply the request-level output limit after capture."""

        if max_bytes < 1:
            raise TerminalRunnerError(
                "max_output_bytes must be positive."
            )

        stdout_bytes = stdout.encode("utf-8")
        stderr_bytes = stderr.encode("utf-8")

        total = len(stdout_bytes) + len(stderr_bytes)

        if total <= max_bytes:
            return stdout, stderr, False

        stdout_budget = max_bytes // 2
        stderr_budget = max_bytes - stdout_budget

        stdout_limited = stdout_bytes[:stdout_budget]
        stderr_limited = stderr_bytes[:stderr_budget]

        return (
            stdout_limited.decode("utf-8", errors="ignore"),
            stderr_limited.decode("utf-8", errors="ignore"),
            True,
        )

    @staticmethod
    def _make_result(
        request: TerminalRequest,
        *,
        status: TerminalExecutionStatus,
        exit_code: int,
        error: str,
    ) -> TerminalResult:
        return TerminalResult(
            status=status,
            argv=tuple(request.argv),
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            working_directory=request.working_directory,
            truncated=False,
            process_id=None,
            error=error,
        )
