
"""Security authorization adapter for FORGEX terminal execution."""

from __future__ import annotations

import inspect
import logging
import shlex
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from forgex.tools.terminal.models import TerminalRequest

logger = logging.getLogger(__name__)


class TerminalSecurityError(Exception):
    """Base exception for terminal security failures."""


class TerminalPolicyError(TerminalSecurityError):
    """Raised when security policy evaluation fails."""


class TerminalApprovalError(TerminalSecurityError):
    """Raised when required approval is unavailable or rejected."""


@dataclass(frozen=True, slots=True)
class TerminalSecurityDecision:
    """Normalized security policy decision."""

    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    risk_level: str = "medium"

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise TypeError("allowed must be bool.")

        if not isinstance(self.requires_approval, bool):
            raise TypeError("requires_approval must be bool.")

        if self.allowed and self.requires_approval:
            raise ValueError(
                "A decision requiring approval cannot be immediately allowed."
            )

        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string.")

        if (
            not isinstance(self.risk_level, str)
            or not self.risk_level.strip()
        ):
            raise ValueError("risk_level must be a non-empty string.")


class PolicyEvaluator(Protocol):
    def __call__(
        self,
        request: TerminalRequest,
        command_text: str,
    ) -> TerminalSecurityDecision | Awaitable[TerminalSecurityDecision]:
        """Evaluate a terminal command."""


class ApprovalHandler(Protocol):
    def __call__(
        self,
        request: TerminalRequest,
        decision: TerminalSecurityDecision,
    ) -> bool | Awaitable[bool]:
        """Request explicit user approval."""


class PolicyTerminalAuthorizer:
    """Authorize terminal commands using policy and approval callbacks."""

    def __init__(
        self,
        *,
        policy_evaluator: PolicyEvaluator,
        approval_handler: ApprovalHandler | None = None,
        workspace: Path | None = None,
    ) -> None:
        if not callable(policy_evaluator):
            raise TypeError("policy_evaluator must be callable.")

        if (
            approval_handler is not None
            and not callable(approval_handler)
        ):
            raise TypeError("approval_handler must be callable.")

        if workspace is not None:
            try:
                resolved_workspace = (
                    Path(workspace).expanduser().resolve(strict=True)
                )
            except (OSError, RuntimeError) as exc:
                raise ValueError(
                    "Configured workspace must exist."
                ) from exc

            if not resolved_workspace.is_dir():
                raise ValueError(
                    "Configured workspace must be a directory."
                )
        else:
            resolved_workspace = None

        self._policy_evaluator = policy_evaluator
        self._approval_handler = approval_handler
        self._workspace = resolved_workspace

    async def authorize(self, request: TerminalRequest) -> bool:
        """Authorize a request, failing closed on every policy error."""

        if not isinstance(request, TerminalRequest):
            raise TypeError("request must be a TerminalRequest.")

        self._validate_workspace(request)
        command_text = self._format_command(request.argv)

        try:
            decision = await self._resolve(
                self._policy_evaluator(request, command_text)
            )
        except Exception as exc:
            logger.exception("Terminal policy evaluation failed.")
            raise TerminalPolicyError(
                "Policy evaluation failed; execution denied."
            ) from exc

        if not isinstance(decision, TerminalSecurityDecision):
            raise TerminalPolicyError(
                "Policy evaluator returned an invalid decision."
            )

        if not decision.allowed and not decision.requires_approval:
            logger.warning(
                "Terminal command denied: subject=%s risk=%s reason=%s",
                request.subject,
                decision.risk_level,
                decision.reason,
            )
            return False

        if decision.requires_approval:
            return await self._request_approval(request, decision)

        return decision.allowed

    async def _request_approval(
        self,
        request: TerminalRequest,
        decision: TerminalSecurityDecision,
    ) -> bool:
        if self._approval_handler is None:
            raise TerminalApprovalError(
                "Command requires explicit approval, but no approval "
                "handler is configured."
            )

        try:
            approved = await self._resolve(
                self._approval_handler(request, decision)
            )
        except Exception as exc:
            logger.exception("Terminal approval failed.")
            raise TerminalApprovalError(
                "Approval could not be verified; execution denied."
            ) from exc

        if not isinstance(approved, bool):
            raise TerminalApprovalError(
                "Approval handler must return a boolean."
            )

        if not approved:
            logger.info(
                "Terminal command approval rejected: subject=%s",
                request.subject,
            )

        return approved

    def _validate_workspace(self, request: TerminalRequest) -> None:
        """Reject paths outside the configured workspace."""

        if self._workspace is None:
            return

        try:
            requested_path = request.working_directory.resolve(
                strict=True
            )
            requested_path.relative_to(self._workspace)
        except (OSError, ValueError, RuntimeError) as exc:
            raise TerminalPolicyError(
                "Working directory is outside the configured workspace."
            ) from exc

        if not requested_path.is_dir():
            raise TerminalPolicyError(
                "Working directory is not a valid directory."
            )

    @staticmethod
    def _format_command(argv: tuple[str, ...]) -> str:
        """Format argv for policy inspection only."""

        if not argv:
            raise TerminalPolicyError(
                "Empty commands are not permitted."
            )

        if any(
            not isinstance(argument, str) or "\x00" in argument
            for argument in argv
        ):
            raise TerminalPolicyError(
                "Invalid command argument."
            )

        return shlex.join(argv)

    @staticmethod
    async def _resolve(value):
        if inspect.isawaitable(value):
            return await value
        return value
