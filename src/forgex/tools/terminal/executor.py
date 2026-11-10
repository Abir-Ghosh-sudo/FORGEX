
"""Secure orchestration layer for FORGEX terminal execution."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from forgex.tools.terminal.models import (
    TerminalExecutionStatus,
    TerminalRequest,
    TerminalResult,
)

logger = logging.getLogger(__name__)


class TerminalAuthorizationError(Exception):
    """Raised when a terminal request is not authorized."""


class TerminalExecutionError(Exception):
    """Raised when the terminal execution pipeline fails."""


class TerminalAuthorizer(Protocol):
    """Authorization contract for terminal requests."""

    def authorize(self, request: TerminalRequest) -> bool | Awaitable[bool]:
        """Return whether the request is permitted."""


class TerminalRunner(Protocol):
    """Runtime execution contract."""

    def run(
        self,
        request: TerminalRequest,
    ) -> TerminalResult | Awaitable[TerminalResult]:
        """Execute a validated terminal request."""


class TerminalAuditSink(Protocol):
    """Audit logging contract."""

    def record(self, result: TerminalResult) -> None | Awaitable[None]:
        """Record a terminal execution result."""


class TerminalExecutor:
    """Coordinates authorization, execution and audit recording.

    The executor never invokes a shell itself. The injected runner is
    responsible for passing argv directly to the runtime supervisor.
    """

    def __init__(
        self,
        *,
        authorizer: TerminalAuthorizer,
        runner: TerminalRunner,
        audit_sink: TerminalAuditSink | None = None,
    ) -> None:
        if authorizer is None:
            raise ValueError("A terminal authorizer is required.")

        if runner is None:
            raise ValueError("A terminal runner is required.")

        self._authorizer = authorizer
        self._runner = runner
        self._audit_sink = audit_sink
        self._closed = False
        self._lock = asyncio.Lock()

    async def execute(self, request: TerminalRequest) -> TerminalResult:
        """Authorize and execute a terminal request."""

        if self._closed:
            raise TerminalExecutionError("Terminal executor is closed.")

        if not isinstance(request, TerminalRequest):
            raise TypeError("request must be a TerminalRequest.")

        async with self._lock:
            if self._closed:
                raise TerminalExecutionError("Terminal executor is closed.")

        self._validate_workspace(request)

        started_at = time.monotonic()

        try:
            authorized = await self._resolve(
                self._authorizer.authorize(request)
            )

            if not authorized:
                result = self._make_result(
                    request=request,
                    status=TerminalExecutionStatus.DENIED,
                    started_at=started_at,
                    error="Terminal execution was denied by security policy.",
                )
                await self._audit(result)
                return result

            result = await self._resolve(self._runner.run(request))

            if not isinstance(result, TerminalResult):
                raise TerminalExecutionError(
                    "Terminal runner returned an invalid result."
                )

            if result.argv != request.argv:
                raise TerminalExecutionError(
                    "Runner result argv does not match the authorized request."
                )

            if result.working_directory.resolve() != (
                request.working_directory.resolve()
            ):
                raise TerminalExecutionError(
                    "Runner executed in an unexpected working directory."
                )

            await self._audit(result)
            return result

        except asyncio.CancelledError:
            logger.info(
                "Terminal execution cancelled: executable=%s session=%s",
                request.executable,
                request.session_id,
            )
            raise

        except TerminalExecutionError:
            raise

        except Exception as exc:
            logger.exception(
                "Terminal execution failed: executable=%s session=%s",
                request.executable,
                request.session_id,
            )

            result = self._make_result(
                request=request,
                status=TerminalExecutionStatus.FAILED,
                started_at=started_at,
                exit_code=-1,
                error=f"{type(exc).__name__}: {exc}",
            )
            await self._audit(result)
            return result

    def _validate_workspace(self, request: TerminalRequest) -> None:
        """Ensure execution starts inside an existing directory."""

        try:
            workspace = request.working_directory.resolve(strict=True)
        except OSError as exc:
            raise TerminalExecutionError(
                f"Working directory does not exist: "
                f"{request.working_directory}"
            ) from exc

        if not workspace.is_dir():
            raise TerminalExecutionError(
                f"Working directory is not a directory: {workspace}"
            )

    async def _audit(self, result: TerminalResult) -> None:
        """Send the result to the optional audit sink."""

        if self._audit_sink is None:
            return

        try:
            await self._resolve(self._audit_sink.record(result))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to record terminal execution audit.")

    @staticmethod
    async def _resolve(value):
        """Resolve synchronous or asynchronous dependency results."""

        if inspect.isawaitable(value):
            return await value
        return value

    @staticmethod
    def _make_result(
        *,
        request: TerminalRequest,
        status: TerminalExecutionStatus,
        started_at: float,
        exit_code: int | None = None,
        error: str | None = None,
    ) -> TerminalResult:
        return TerminalResult(
            status=status,
            argv=request.argv,
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_seconds=max(0.0, time.monotonic() - started_at),
            working_directory=request.working_directory,
            error=error,
        )

    async def close(self) -> None:
        """Prevent new terminal executions."""

        async with self._lock:
            self._closed = True

    @property
    def is_closed(self) -> bool:
        """Whether the executor has been closed."""

        return self._closed
