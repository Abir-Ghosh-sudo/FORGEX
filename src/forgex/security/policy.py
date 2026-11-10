
"""Centralized security policy engine for FORGEX."""

from __future__ import annotations

import fnmatch
import re
import shlex
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from forgex.security.permissions import (
    PermissionAction,
    PermissionDecision,
    PermissionLevel,
    PermissionManager,
    PermissionRequest,
    RiskLevel,
)


class OperationType(StrEnum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    FILE_EXECUTE = "file_execute"

    TERMINAL_READ = "terminal_read"
    TERMINAL_EXECUTE = "terminal_execute"

    GIT_READ = "git_read"
    GIT_WRITE = "git_write"
    GIT_DESTRUCTIVE = "git_destructive"

    NETWORK_READ = "network_read"
    NETWORK_WRITE = "network_write"

    PACKAGE_INSTALL = "package_install"
    PACKAGE_REMOVE = "package_remove"

    CONFIG_READ = "config_read"
    CONFIG_WRITE = "config_write"

    ADMIN = "admin"


class PolicyMode(StrEnum):
    STRICT = "strict"
    BALANCED = "balanced"
    PERMISSIVE = "permissive"


@dataclass(frozen=True, slots=True)
class SecurityRule:
    """A configurable rule for classifying and enforcing operations."""

    name: str
    operation: OperationType
    risk: RiskLevel
    action: PermissionAction
    enabled: bool = True
    resource_patterns: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Security rule name cannot be empty.")

        if not self.resource_patterns:
            object.__setattr__(self, "resource_patterns", ("*",))


@dataclass(frozen=True, slots=True)
class SecurityPolicyConfig:
    """Immutable configuration for security policy enforcement."""

    mode: PolicyMode = PolicyMode.STRICT
    workspace: Path | None = None
    protected_paths: tuple[str, ...] = (
        ".git",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa",
        "id_ed25519",
    )
    blocked_commands: tuple[str, ...] = (
        "format",
        "shutdown",
        "restart-computer",
        "remove-item",
        "rm",
        "rmdir",
        "del",
        "diskpart",
        "reg",
        "regedit",
    )
    require_terminal_approval: bool = True
    require_network_approval: bool = True
    allow_network: bool = False
    allow_package_install: bool = True
    max_command_length: int = 10_000

    def __post_init__(self) -> None:
        if self.max_command_length < 1:
            raise ValueError("Maximum command length must be positive.")

        if self.workspace is not None:
            object.__setattr__(
                self,
                "workspace",
                self.workspace.expanduser().resolve(strict=False),
            )


@dataclass(frozen=True, slots=True)
class SecurityEvaluation:
    """Complete result of a security policy evaluation."""

    operation: OperationType
    risk: RiskLevel
    decision: PermissionDecision
    matched_rule: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    @property
    def requires_approval(self) -> bool:
        return self.decision.action == PermissionAction.ASK


class SecurityPolicy:
    """Central policy engine for classifying and evaluating operations."""

    _RISK_ORDER = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.CRITICAL: 3,
    }

    _SHELL_META = re.compile(r"[;&|`$<>]")

    _DANGEROUS_PATTERNS = (
        re.compile(r"(?i)\brm\s+-[a-z]*r[a-z]*f[a-z]*\s+/"),
        re.compile(r"(?i)\bformat\s+[a-z]:"),
        re.compile(r"(?i)\bdiskpart\b"),
        re.compile(r"(?i)\bshutdown\b"),
        re.compile(r"(?i)\bmkfs(?:\.[a-z0-9]+)?\b"),
        re.compile(r"(?i)\bdd\s+.*\bof=/dev/"),
        re.compile(r"(?i)\b(?:sudo\s+)?chmod\s+-R\s+777\b"),
        re.compile(r"(?i)\b(?:sudo\s+)?chown\s+-R\b"),
        re.compile(r"(?i)\b(?:Invoke-WebRequest|iwr)\b.*\b(?:iex|Invoke-Expression)\b"),
        re.compile(r"(?i)\b(?:curl|wget)\b.*\|\s*(?:sh|bash|zsh)\b"),
    )

    def __init__(
        self,
        permission_manager: PermissionManager,
        config: SecurityPolicyConfig | None = None,
        rules: Iterable[SecurityRule] | None = None,
    ) -> None:
        self._permissions = permission_manager
        self._config = config or SecurityPolicyConfig()
        self._rules = list(rules or self._default_rules())

        self._validate_rules()

    @property
    def config(self) -> SecurityPolicyConfig:
        return self._config

    @property
    def rules(self) -> tuple[SecurityRule, ...]:
        return tuple(self._rules)

    def add_rule(self, rule: SecurityRule) -> None:
        """Add a named rule without allowing duplicate names."""

        if any(existing.name == rule.name for existing in self._rules):
            raise ValueError(f"Security rule already exists: {rule.name}")

        self._rules.append(rule)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name."""

        original_length = len(self._rules)

        self._rules = [
            rule for rule in self._rules
            if rule.name != name
        ]

        return len(self._rules) != original_length

    def evaluate(
        self,
        *,
        subject: str,
        operation: OperationType,
        resource: str,
        workspace: Path | None = None,
        command: str | None = None,
    ) -> SecurityEvaluation:
        """Evaluate an operation against policy and permission grants."""

        warnings: list[str] = []
        normalized_resource = resource.strip()

        if not subject.strip() or not normalized_resource:
            return self._result(
                operation,
                RiskLevel.CRITICAL,
                PermissionDecision.deny(
                    "Subject and resource must be non-empty."
                ),
                warnings=("Invalid permission request.",),
            )

        effective_workspace = workspace or self._config.workspace

        if effective_workspace is not None:
            effective_workspace = effective_workspace.expanduser().resolve(
                strict=False
            )

        if command is not None:
            command_result = self.inspect_command(command)

            if command_result is not None:
                risk, reason = command_result

                return self._result(
                    operation,
                    risk,
                    PermissionDecision.deny(reason),
                    warnings=(reason,),
                )

        path_result = self._inspect_protected_path(
            normalized_resource,
            effective_workspace,
        )

        if path_result is not None:
            return self._result(
                operation,
                RiskLevel.CRITICAL,
                PermissionDecision.deny(path_result),
                warnings=(path_result,),
            )

        matched_rule = self._find_rule(operation, normalized_resource)

        if matched_rule is not None:
            if matched_rule.action == PermissionAction.DENY:
                return self._result(
                    operation,
                    matched_rule.risk,
                    PermissionDecision.deny(
                        f"Blocked by security rule: {matched_rule.name}"
                    ),
                    matched_rule.name,
                )

            if matched_rule.action == PermissionAction.ASK:
                return self._result(
                    operation,
                    matched_rule.risk,
                    PermissionDecision.ask(
                        f"Approval required by security rule: {matched_rule.name}"
                    ),
                    matched_rule.name,
                )

        risk = (
            matched_rule.risk
            if matched_rule is not None
            else self._infer_risk(operation)
        )

        restriction = self._check_config_restrictions(operation, risk)

        if restriction is not None:
            return self._result(
                operation,
                risk,
                restriction,
                matched_rule.name if matched_rule else None,
                tuple(warnings),
            )

        permission_level = self._required_permission(operation)

        decision = self._permissions.check(
            PermissionRequest(
                subject=subject,
                resource=normalized_resource,
                action=permission_level,
                workspace=effective_workspace,
                risk=risk,
            )
        )

        if (
            decision.action == PermissionAction.DENY
            and self._config.mode == PolicyMode.PERMISSIVE
            and risk == RiskLevel.LOW
        ):
            warnings.append(
                "Permissive mode does not override explicit permission denial."
            )

        return self._result(
            operation,
            risk,
            decision,
            matched_rule.name if matched_rule else None,
            tuple(warnings),
        )

    def inspect_command(
        self,
        command: str,
    ) -> tuple[RiskLevel, str] | None:
        """Inspect a shell command for known dangerous patterns.

        This is heuristic detection, not a shell sandbox.
        """

        if not command or not command.strip():
            return RiskLevel.HIGH, "Empty terminal commands are not permitted."

        if len(command) > self._config.max_command_length:
            return RiskLevel.HIGH, "Command exceeds the configured length limit."

        normalized = command.strip()

        for pattern in self._DANGEROUS_PATTERNS:
            if pattern.search(normalized):
                return (
                    RiskLevel.CRITICAL,
                    "Command matches a blocked dangerous-operation pattern.",
                )

        try:
            tokens = shlex.split(normalized, posix=False)
        except ValueError:
            return RiskLevel.HIGH, "Command could not be safely parsed."

        if not tokens:
            return RiskLevel.HIGH, "Command contains no executable."

        executable = Path(tokens[0].strip('"')).name.lower()

        if executable in {item.lower() for item in self._config.blocked_commands}:
            return (
                RiskLevel.CRITICAL,
                f"Executable is blocked by security configuration: {executable}",
            )

        if self._SHELL_META.search(normalized):
            return (
                RiskLevel.HIGH,
                "Shell operators require a separately approved command.",
            )

        return None

    def _inspect_protected_path(
        self,
        resource: str,
        workspace: Path | None,
    ) -> str | None:
        """Detect protected files and paths inside the workspace."""

        candidate = Path(resource).expanduser()

        if not candidate.is_absolute():
            if workspace is None:
                return None

            candidate = workspace / candidate

        resolved = candidate.resolve(strict=False)

        if workspace is not None:
            try:
                resolved.relative_to(workspace)
            except ValueError:
                return "Resource is outside the authorized workspace."

        relative = (
            resolved.relative_to(workspace)
            if workspace is not None
            else resolved
        )

        path_parts = relative.parts

        for protected in self._config.protected_paths:
            if any(
                fnmatch.fnmatchcase(part.lower(), protected.lower())
                for part in path_parts
            ):
                return f"Access to protected path is blocked: {protected}"

        return None

    def _check_config_restrictions(
        self,
        operation: OperationType,
        risk: RiskLevel,
    ) -> PermissionDecision | None:
        """Enforce non-overridable configuration restrictions."""

        if operation in {
            OperationType.NETWORK_READ,
            OperationType.NETWORK_WRITE,
        }:
            if not self._config.allow_network:
                return PermissionDecision.deny(
                    "Network access is disabled by security configuration."
                )

            if self._config.require_network_approval:
                return PermissionDecision.ask(
                    "Network access requires explicit approval."
                )

        if operation in {
            OperationType.TERMINAL_EXECUTE,
            OperationType.FILE_EXECUTE,
        } and self._config.require_terminal_approval:
            return PermissionDecision.ask(
                "Execution requires explicit terminal approval."
            )

        if (
            operation == OperationType.PACKAGE_INSTALL
            and not self._config.allow_package_install
        ):
            return PermissionDecision.deny(
                "Package installation is disabled by security configuration."
            )

        if (
            self._config.mode == PolicyMode.STRICT
            and risk == RiskLevel.HIGH
        ):
            return PermissionDecision.ask(
                "High-risk operation requires approval in strict mode."
            )

        return None

    def _find_rule(
        self,
        operation: OperationType,
        resource: str,
    ) -> SecurityRule | None:
        """Find the first matching enabled rule."""

        for rule in self._rules:
            if not rule.enabled or rule.operation != operation:
                continue

            if any(
                fnmatch.fnmatchcase(resource, pattern)
                for pattern in rule.resource_patterns
            ):
                return rule

        return None

    def _required_permission(
        self,
        operation: OperationType,
    ) -> PermissionLevel:
        """Map operation types to required permission levels."""

        if operation in {
            OperationType.FILE_READ,
            OperationType.GIT_READ,
            OperationType.TERMINAL_READ,
            OperationType.NETWORK_READ,
            OperationType.CONFIG_READ,
        }:
            return PermissionLevel.READ

        if operation in {
            OperationType.FILE_WRITE,
            OperationType.FILE_DELETE,
            OperationType.GIT_WRITE,
            OperationType.NETWORK_WRITE,
            OperationType.CONFIG_WRITE,
            OperationType.PACKAGE_INSTALL,
            OperationType.PACKAGE_REMOVE,
        }:
            return PermissionLevel.WRITE

        if operation in {
            OperationType.FILE_EXECUTE,
            OperationType.TERMINAL_EXECUTE,
        }:
            return PermissionLevel.EXECUTE

        if operation in {
            OperationType.GIT_DESTRUCTIVE,
            OperationType.ADMIN,
        }:
            return PermissionLevel.ADMIN

        return PermissionLevel.NONE

    def _infer_risk(self, operation: OperationType) -> RiskLevel:
        """Infer a baseline risk level for an operation."""

        risk_map = {
            OperationType.FILE_READ: RiskLevel.LOW,
            OperationType.GIT_READ: RiskLevel.LOW,
            OperationType.CONFIG_READ: RiskLevel.LOW,
            OperationType.TERMINAL_READ: RiskLevel.LOW,
            OperationType.FILE_WRITE: RiskLevel.MEDIUM,
            OperationType.GIT_WRITE: RiskLevel.MEDIUM,
            OperationType.CONFIG_WRITE: RiskLevel.HIGH,
            OperationType.FILE_DELETE: RiskLevel.HIGH,
            OperationType.TERMINAL_EXECUTE: RiskLevel.HIGH,
            OperationType.FILE_EXECUTE: RiskLevel.HIGH,
            OperationType.GIT_DESTRUCTIVE: RiskLevel.CRITICAL,
            OperationType.NETWORK_READ: RiskLevel.HIGH,
            OperationType.NETWORK_WRITE: RiskLevel.HIGH,
            OperationType.PACKAGE_INSTALL: RiskLevel.HIGH,
            OperationType.PACKAGE_REMOVE: RiskLevel.HIGH,
            OperationType.ADMIN: RiskLevel.CRITICAL,
        }

        return risk_map[operation]

    @staticmethod
    def _result(
        operation: OperationType,
        risk: RiskLevel,
        decision: PermissionDecision,
        matched_rule: str | None = None,
        warnings: tuple[str, ...] = (),
    ) -> SecurityEvaluation:
        return SecurityEvaluation(
            operation=operation,
            risk=risk,
            decision=decision,
            matched_rule=matched_rule,
            warnings=warnings,
        )

    def _default_rules(self) -> list[SecurityRule]:
        """Build default operation rules."""

        return [
            SecurityRule(
                name="block-destructive-git",
                operation=OperationType.GIT_DESTRUCTIVE,
                risk=RiskLevel.CRITICAL,
                action=PermissionAction.ASK,
                description="Destructive Git operations require approval.",
            ),
            SecurityRule(
                name="protect-administration",
                operation=OperationType.ADMIN,
                risk=RiskLevel.CRITICAL,
                action=PermissionAction.ASK,
                description="Administrative operations require approval.",
            ),
            SecurityRule(
                name="protect-package-removal",
                operation=OperationType.PACKAGE_REMOVE,
                risk=RiskLevel.HIGH,
                action=PermissionAction.ASK,
                description="Removing packages requires approval.",
            ),
        ]

    def _validate_rules(self) -> None:
        """Validate configured rule uniqueness."""

        names = [rule.name for rule in self._rules]

        if len(names) != len(set(names)):
            raise ValueError("Security rule names must be unique.")
