
"""Security gateway for controlled runtime command execution.

All command execution must pass through this gateway. It fails closed:
missing policy evaluation or required approval means the command is not run.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class SecurityGatewayError(RuntimeError):
    """Base exception for runtime security failures."""


class PolicyUnavailableError(SecurityGatewayError):
    """Raised when no security policy evaluator is configured."""


class CommandDeniedError(SecurityGatewayError):
    """Raised when a command is denied by security policy."""


class ApprovalRequiredError(SecurityGatewayError):
    """Raised when approval is required but unavailable or rejected."""


class CommandExecutionError(SecurityGatewayError):
    """Raised when the configured command executor fails."""


@dataclass(frozen=True, slots=True)
class CommandRequest:
    """A request to execute a command."""

    command: str
    workspace: Path
    timeout: float = 120.0
    environment: dict[str, str] = field(default_factory=dict)
    subject: str = "forgex-agent"
    session_id: str | None = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.command or not self.command.strip():
            raise ValueError("Command cannot be empty.")

        if "\x00" in self.command:
            raise ValueError("Command contains a null byte.")

        if self.timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        if not self.subject.strip():
            raise ValueError("Command subject cannot be empty.")

        workspace = Path(self.workspace).expanduser().resolve()

        if not workspace.exists() or not workspace.is_dir():
            raise ValueError(f"Workspace is not a valid directory: {workspace}")

        for key, value in self.environment.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("Environment keys and values must be strings.")
            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError("Invalid environment variable.")

        object.__setattr__(self, "workspace", workspace)
        object.__setattr__(self, "environment", dict(self.environment))


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Normalized result returned by a policy evaluator."""

    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    risk: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    """Normalized result returned by an approval handler."""

    approved: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """Security and execution metadata for a command."""

    request_id: str
    subject: str
    workspace: str
    command: str
    risk: str
    approved: bool
    started_at: float
    finished_at: float
    success: bool
    error: str | None = None


class PolicyEvaluator(Protocol):
    def __call__(
        self,
        request: CommandRequest,
    ) -> PolicyResult | Awaitable[PolicyResult]:
        ...


class ApprovalHandler(Protocol):
    def __call__(
        self,
        request: CommandRequest,
        policy: PolicyResult,
    ) -> ApprovalResult | Awaitable[ApprovalResult]:
        ...


class CommandExecutor(Protocol):
    def __call__(
        self,
        request: CommandRequest,
    ) -> Any | Awaitable[Any]:
        ...


class AuditHandler(Protocol):
    def __call__(
        self,
        record: ExecutionRecord,
    ) -> Any | Awaitable[Any]:
        ...


async def _resolve(value: Any) -> Any:
    """Resolve synchronous and asynchronous callback results."""
    if inspect.isawaitable(value):
        return await value
    return value


class SecurityGateway:
    """Fail-closed security boundary for runtime command execution.

    The gateway does not execute shell commands itself. It delegates to an
    injected executor only after policy evaluation and required approval.

    Integrate existing SecurityPolicy, ApprovalManager, RuntimeManager and
    audit infrastructure through the callback interfaces.
    """

    def __init__(
        self,
        *,
        policy_evaluator: PolicyEvaluator | None,
        command_executor: CommandExecutor,
        approval_handler: ApprovalHandler | None = None,
        audit_handler: AuditHandler | None = None,
        max_command_length: int = 10_000,
        max_concurrent_commands: int = 4,
    ) -> None:
        if policy_evaluator is None:
            raise PolicyUnavailableError(
                "A security policy evaluator is required."
            )

        if not callable(command_executor):
            raise TypeError("command_executor must be callable.")

        if max_command_length < 1:
            raise ValueError("max_command_length must be positive.")

        if max_concurrent_commands < 1:
            raise ValueError("max_concurrent_commands must be positive.")

        self._policy_evaluator = policy_evaluator
        self._command_executor = command_executor
        self._approval_handler = approval_handler
        self._audit_handler = audit_handler

        self._max_command_length = max_command_length
        self._semaphore = asyncio.Semaphore(max_concurrent_commands)
        self._closed = False

    async def execute(self, request: CommandRequest) -> Any:
        """Authorize, approve and execute a command."""

        if self._closed:
            raise SecurityGatewayError("Security gateway is closed.")

        if len(request.command) > self._max_command_length:
            raise CommandDeniedError("Command exceeds the configured length limit.")

        async with self._semaphore:
            return await self._execute_authorized(request)

    async def _execute_authorized(self, request: CommandRequest) -> Any:
        started_at = time.time()
        policy_result: PolicyResult | None = None
        approved = False
        success = False
        error_message: str | None = None

        try:
            policy_result = await _resolve(
                self._policy_evaluator(request)
            )

            if not isinstance(policy_result, PolicyResult):
                raise PolicyUnavailableError(
                    "Policy evaluator returned an invalid result."
                )

            if not policy_result.allowed:
                raise CommandDeniedError(
                    policy_result.reason or "Command denied by security policy."
                )

            if policy_result.requires_approval:
                if self._approval_handler is None:
                    raise ApprovalRequiredError(
                        "This command requires approval, but no approval "
                        "handler is configured."
                    )

                approval = await _resolve(
                    self._approval_handler(request, policy_result)
                )

                if not isinstance(approval, ApprovalResult):
                    raise ApprovalRequiredError(
                        "Approval handler returned an invalid result."
                    )

                if not approval.approved:
                    raise ApprovalRequiredError(
                        approval.reason or "Command approval was rejected."
                    )

                approved = True

            result = await _resolve(self._command_executor(request))
            success = True
            return result

        except asyncio.CancelledError:
            error_message = "Command execution cancelled."
            raise

        except SecurityGatewayError as exc:
            error_message = str(exc)
            raise

        except Exception as exc:
            error_message = str(exc)
            logger.exception(
                "Command execution failed (request_id=%s)",
                request.request_id,
            )
            raise CommandExecutionError(
                f"Command execution failed: {exc}"
            ) from exc

        finally:
            record = ExecutionRecord(
                request_id=request.request_id,
                subject=request.subject,
                workspace=str(request.workspace),
                command=request.command,
                risk=policy_result.risk if policy_result else "unknown",
                approved=approved,
                started_at=started_at,
                finished_at=time.time(),
                success=success,
                error=error_message,
            )

            await self._write_audit(record)

    async def _write_audit(self, record: ExecutionRecord) -> None:
        """Write an execution record without masking the original result."""

        if self._audit_handler is None:
            logger.info(
                "Command audit: request_id=%s subject=%s risk=%s "
                "approved=%s success=%s",
                record.request_id,
                record.subject,
                record.risk,
                record.approved,
                record.success,
            )
            return

        try:
            await _resolve(self._audit_handler(record))
        except Exception:
            logger.exception(
                "Failed to write command audit record (request_id=%s)",
                record.request_id,
            )

    async def close(self) -> None:
        """Prevent new commands from entering the gateway."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed
