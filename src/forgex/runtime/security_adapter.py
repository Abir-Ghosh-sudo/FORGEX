
"""Adapters connecting FORGEX security policy and runtime infrastructure."""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any, Callable

from forgex.runtime.manager import RuntimeManager
from forgex.runtime.security import (
    ApprovalRequiredError,
    ApprovalResult,
    CommandRequest,
    PolicyResult,
    SecurityGateway,
)
from forgex.security.permissions import RiskLevel
from forgex.security.policy import SecurityPolicy

logger = logging.getLogger(__name__)


class SecurityAdapterError(RuntimeError):
    """Raised when security integration fails."""


def _is_async_callable(callback: Callable[..., Any]) -> bool:
    """Check whether a callback is asynchronous."""
    return inspect.iscoroutinefunction(callback)


class RuntimeSecurityAdapter:
    """Integrate policy evaluation, approval and runtime execution."""

    def __init__(
        self,
        *,
        policy: SecurityPolicy,
        runtime: RuntimeManager,
        approval_handler: Callable[..., Any] | None = None,
        audit_handler: Callable[..., Any] | None = None,
        max_concurrent_commands: int = 4,
    ) -> None:
        if not isinstance(policy, SecurityPolicy):
            raise TypeError("policy must be a SecurityPolicy instance.")

        if not isinstance(runtime, RuntimeManager):
            raise TypeError("runtime must be a RuntimeManager instance.")

        self.policy = policy
        self.runtime = runtime
        self.approval_handler = approval_handler
        self.audit_handler = audit_handler

        self.gateway = SecurityGateway(
            policy_evaluator=self._evaluate_policy,
            approval_handler=self._request_approval,
            command_executor=self._execute_command,
            audit_handler=audit_handler,
            max_concurrent_commands=max_concurrent_commands,
        )

    def _evaluate_policy(self, request: CommandRequest) -> PolicyResult:
        """Evaluate a command using the configured security policy."""

        evaluation = self.policy.evaluate(
            subject=request.subject,
            resource=request.command,
            operation=self._operation_type(),
            workspace=request.workspace,
        )

        return PolicyResult(
            allowed=bool(evaluation.allowed),
            requires_approval=bool(evaluation.requires_approval),
            reason=str(getattr(evaluation, "reason", "")),
            risk=str(getattr(evaluation, "risk", "unknown")),
            metadata={
                "request_id": request.request_id,
                "matched_rule": getattr(evaluation, "matched_rule", None),
            },
        )

    def _operation_type(self) -> Any:
        """Resolve the terminal execution operation."""
        from forgex.security.policy import OperationType

        return OperationType.TERMINAL_EXECUTE

    async def _request_approval(
        self,
        request: CommandRequest,
        policy: PolicyResult,
    ) -> ApprovalResult:
        """Request explicit approval before executing a command."""

        if self.approval_handler is None:
            raise ApprovalRequiredError(
                "No approval handler is configured."
            )

        result = self.approval_handler(request, policy)

        if inspect.isawaitable(result):
            result = await result

        if isinstance(result, ApprovalResult):
            return result

        if isinstance(result, bool):
            return ApprovalResult(
                approved=result,
                reason="Approved by user." if result else "Approval rejected.",
            )

        raise SecurityAdapterError(
            "Approval handler must return ApprovalResult or bool."
        )

    async def _execute_command(self, request: CommandRequest) -> Any:
        """Execute an approved command through RuntimeManager."""

        result = await self.runtime.execute_shell(
            request.command,
            cwd=request.workspace,
            timeout=request.timeout,
            env=request.environment,
        )

        return result

    async def execute(
        self,
        command: str,
        *,
        workspace: Path,
        subject: str = "forgex-agent",
        timeout: float = 120.0,
        environment: dict[str, str] | None = None,
        session_id: str | None = None,
    ) -> Any:
        """Execute a command through the complete security pipeline."""

        request = CommandRequest(
            command=command,
            workspace=workspace,
            subject=subject,
            timeout=timeout,
            environment=environment or {},
            session_id=session_id,
        )

        return await self.gateway.execute(request)

    async def close(self) -> None:
        """Close the security gateway."""
        await self.gateway.close()

    @property
    def is_closed(self) -> bool:
        return self.gateway.is_closed
