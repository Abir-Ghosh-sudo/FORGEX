"""Secure orchestration layer for FORGEX terminal execution."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable
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
    def authorize(self, request: TerminalRequest) -> bool | Awaitable[bool]:
        """Return whether the request is permitted."""


class TerminalRunner(Protocol):
    def run(
        self,
        request: TerminalRequest,
    ) -> TerminalResult | Awaitable[TerminalResult]:
        """Execute an authorized request."""


class TerminalAuditSink(Protocol):
    def record(
        self,
        result: TerminalResult,
    ) -> None | Awaitable[None]:
        """Record an execution result."""


class TerminalExecutor:
    """Coordinates authorization, execution and audit recording."""

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
        self._active_executions = 0
        self._state_lock = asyncio.Lock()
        self._idle = asyncio.Event()
        self._idle.set()

    async def execute(self, request: TerminalRequest) -> TerminalResult:
        """Authorize and execute a terminal request."""

        if not isinstance(request, TerminalRequest):
            raise TypeError("request must be a TerminalRequest.")

        await self._register_execution()

        started_at = time.monotonic()

        try:
            self._validate_workspace(request)

            authorized = await self._resolve(self._authorizer.authorize(request))

            if not isinstance(authorized, bool):
                raise TerminalExecutionError("Authorizer must return a boolean decision.")

            if not authorized:
                result = self._make_result(
                    request=request,
                    status=TerminalExecutionStatus.DENIED,
                    started_at=started_at,
                    error="Terminal execution denied by security policy.",
                )
                await self._audit(result)
                return result

            result = await self._resolve(self._runner.run(request))

            self._validate_result(request, result)

            await self._audit(result)
            return result

        except asyncio.CancelledError:
            logger.info(
                "Terminal execution cancelled: session=%s",
                request.session_id,
            )
            raise

        except TerminalExecutionError:
            raise

        except Exception as exc:
            logger.exception(
                "Terminal execution failed: session=%s",
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

        finally:
            await self._unregister_execution()

    async def _register_execution(self) -> None:
        async with self._state_lock:
            if self._closed:
                raise TerminalExecutionError("Terminal executor is closed.")

            self._active_executions += 1
            self._idle.clear()

    async def _unregister_execution(self) -> None:
        async with self._state_lock:
            self._active_executions -= 1

            if self._active_executions <= 0:
                self._active_executions = 0
                self._idle.set()

    @staticmethod
    def _validate_workspace(request: TerminalRequest) -> None:
        """Ensure the working directory exists and is a directory."""

        try:
            workspace = request.working_directory.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise TerminalExecutionError(
                f"Invalid working directory: {request.working_directory}"
            ) from exc

        if not workspace.is_dir():
            raise TerminalExecutionError(f"Working directory is not a directory: {workspace}")

    @staticmethod
    def _validate_result(
        request: TerminalRequest,
        result: TerminalResult,
    ) -> None:
        if not isinstance(result, TerminalResult):
            raise TerminalExecutionError("Terminal runner returned an invalid result.")

        if result.argv != request.argv:
            raise TerminalExecutionError("Runner argv differs from the authorized request.")

        try:
            actual = result.working_directory.resolve(strict=True)
            expected = request.working_directory.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise TerminalExecutionError(
                "Could not verify the execution working directory."
            ) from exc

        if actual != expected:
            raise TerminalExecutionError("Runner used an unexpected working directory.")

    async def _audit(self, result: TerminalResult) -> None:
        """Record an execution result without masking its outcome."""

        if self._audit_sink is None:
            return

        try:
            await self._resolve(self._audit_sink.record(result))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Terminal audit recording failed.")

    @staticmethod
    async def _resolve(value):
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
            duration_seconds=max(
                0.0,
                time.monotonic() - started_at,
            ),
            working_directory=request.working_directory,
            error=error,
        )

    async def close(self, *, wait: bool = True) -> None:
        """Reject new executions and optionally wait for active ones."""

        async with self._state_lock:
            self._closed = True
            idle = self._idle

        if wait:
            await idle.wait()

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def active_executions(self) -> int:
        return self._active_executions
