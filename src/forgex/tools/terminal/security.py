
"""Security authorization adapter for FORGEX terminal execution."""

from __future__ import annotations

import inspect
import logging
import shlex
from collections.abc import Awaitable, Callable
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
        if self.allowed and self.requires_approval:
            raise ValueError(
                "A decision requiring approval cannot be immediately allowed."
            )

        if not self.risk_level.strip():
            raise ValueError("risk_level cannot be empty.")


class PolicyEvaluator(Protocol):
    """Contract for an injected FORGEX security policy evaluator."""

    def __call__(
        self,
        request: TerminalRequest,
        command_text: str,
    ) -> TerminalSecurityDecision | Awaitable[TerminalSecurityDecision]:
        ...


class ApprovalHandler(Protocol):
    """Contract for an interactive approval handler."""

    def __call__(
        self,
        request: TerminalRequest,
        decision: TerminalSecurityDecision,
    ) -> bool | Awaitable[bool]:
        ...


class PolicyTerminalAuthorizer:
    """Authorize terminal requests using policy and approval callbacks.

    This adapter deliberately does not guess the signature of SecurityPolicy.
    An integration layer must translate its evaluation into
    TerminalSecurityDecision.
    """

    def __init__(
        self,
        *,
        policy_evaluator: PolicyEvaluator,
        approval_handler: ApprovalHandler | None = None,
        workspace: Path | None = None,
    ) -> None:
        if not callable(policy_evaluator):
            raise TypeError("policy_evaluator must be callable.")

        if approval_handler is not None and not callable(approval_handler):
            raise TypeError("approval_handler must be callable.")

        self._policy_evaluator = policy_evaluator
        self._approval_handler = approval_handler
        self._workspace = (
            Path(workspace).expanduser().resolve()
            if workspace is not None
            else None
        )

    async def authorize(self, request: TerminalRequest) -> bool:
        """Return True only when policy and required approval both pass."""

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
                "Terminal policy evaluation failed; execution denied."
            ) from exc

        if not isinstance(decision, TerminalSecurityDecision):
            raise TerminalPolicyError(
                "Policy evaluator returned an invalid decision."
            )

        if not decision.allowed and not decision.requires_approval:
            logger.warning(
                "Terminal command denied: subject=%s reason=%s",
                request.subject,
                decision.reason,
            )
            return False

        if decision.requires_approval:
            if self._approval_handler is None:
                raise TerminalApprovalError(
                    "This command requires approval, but no approval "
                    "handler is configured."
                )

            try:
                approved = await self._resolve(
                    self._approval_handler(request, decision)
                )
            except Exception as exc:
                logger.exception("Terminal approval handler failed.")
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
                return False

            return True

        return decision.allowed

    def _validate_workspace(self, request: TerminalRequest) -> None:
        """Prevent requests from escaping the configured workspace."""

        if self._workspace is None:
            return

        try:
            requested_path = request.working_directory.resolve(strict=True)
            requested_path.relative_to(self._workspace)
        except (OSError, ValueError) as exc:
            raise TerminalPolicyError(
                "Working directory is outside the configured workspace."
            ) from exc

    @staticmethod
    def _format_command(argv: tuple[str, ...]) -> str:
        """Create a readable command representation for policy inspection."""

        if not argv:
            raise TerminalPolicyError("Empty command is not permitted.")

        if any("\x00" in argument for argument in argv):
            raise TerminalPolicyError("Null bytes are not permitted.")

        # This is for policy inspection only. Execution must use argv directly.
        return shlex.join(argv)

    @staticmethod
    async def _resolve(value):
        """Resolve synchronous and asynchronous callback results."""

        if inspect.isawaitable(value):
            return await value
        return value
