
"""Centralized security policy engine for FORGEX.

Security policy enforcement for filesystem, terminal, Git, network,
package, and administrative operations.

Command inspection is defense-in-depth, not an OS-level sandbox.
All actual command execution must additionally pass through the
FORGEX sandbox and approval system.
"""

from __future__ import annotations

import base64
import binascii
import fnmatch
import os
import re
import shlex
import threading
from dataclasses import dataclass
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
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Security rule name cannot be empty.")

        if not isinstance(self.operation, OperationType):
            raise TypeError("Invalid security rule operation.")

        if not isinstance(self.risk, RiskLevel):
            raise TypeError("Invalid security rule risk.")

        if not isinstance(self.action, PermissionAction):
            raise TypeError("Invalid security rule action.")

        if not isinstance(self.enabled, bool):
            raise TypeError("Rule enabled must be a boolean.")

        patterns = tuple(self.resource_patterns)

        if any(
            not isinstance(pattern, str) or not pattern.strip()
            for pattern in patterns
        ):
            raise ValueError("Resource patterns must be non-empty strings.")

        object.__setattr__(
            self,
            "resource_patterns",
            patterns or ("*",),
        )

        if not isinstance(self.description, str):
            raise TypeError("Rule description must be a string.")


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
        "remove-itemproperty",
        "clear-content",
        "stop-computer",
        "restart-service",
        "stop-service",
        "rm",
        "rmdir",
        "del",
        "erase",
        "diskpart",
        "reg",
        "regedit",
        "mkfs",
        "dd",
    )

    require_terminal_approval: bool = True
    require_network_approval: bool = True
    allow_network: bool = False
    allow_package_install: bool = True

    max_command_length: int = 10_000

    def __post_init__(self) -> None:
        if not isinstance(self.mode, PolicyMode):
            raise TypeError("mode must be a PolicyMode.")

        if self.max_command_length < 1:
            raise ValueError("Maximum command length must be positive.")

        for name in (
            "require_terminal_approval",
            "require_network_approval",
            "allow_network",
            "allow_package_install",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean.")

        if self.workspace is not None:
            object.__setattr__(
                self,
                "workspace",
                Path(self.workspace).expanduser().resolve(strict=False),
            )

        protected = tuple(self.protected_paths)
        blocked = tuple(self.blocked_commands)

        if any(not isinstance(item, str) or not item.strip()
               for item in protected):
            raise ValueError("Protected paths must be non-empty strings.")

        if any(not isinstance(item, str) or not item.strip()
               for item in blocked):
            raise ValueError("Blocked commands must be non-empty strings.")

        object.__setattr__(self, "protected_paths", protected)
        object.__setattr__(
            self,
            "blocked_commands",
            tuple(item.casefold() for item in blocked),
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

    _SHELL_META = re.compile(r"[;&|`$<>]")

    _DESTRUCTIVE_COMMANDS = frozenset({
        "remove-item",
        "remove-itemproperty",
        "clear-content",
        "clear-item",
        "stop-computer",
        "restart-computer",
        "stop-service",
        "restart-service",
        "format",
        "diskpart",
        "reg",
        "regedit",
        "del",
        "erase",
        "rmdir",
        "rd",
        "rm",
        "mkfs",
        "dd",
        "shred",
    })

    _SHELL_EXECUTABLES = frozenset({
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "cmd",
        "cmd.exe",
        "bash",
        "bash.exe",
        "sh",
        "sh.exe",
        "zsh",
        "zsh.exe",
        "wsl",
        "wsl.exe",
    })

    _DANGEROUS_PATTERNS = (
        re.compile(r"(?i)\brm\s+-[a-z]*r[a-z]*f[a-z]*\s+/"),
        re.compile(r"(?i)\bformat(?:\.com)?\s+[a-z]:"),
        re.compile(r"(?i)\bdiskpart\b"),
        re.compile(r"(?i)\bshutdown(?:\.exe)?\b"),
        re.compile(r"(?i)\bmkfs(?:\.[a-z0-9]+)?\b"),
        re.compile(r"(?i)\bdd\s+.*\bof=/dev/"),
        re.compile(r"(?i)\b(?:sudo\s+)?chmod\s+-R\s+777\b"),
        re.compile(r"(?i)\b(?:sudo\s+)?chown\s+-R\b"),
        re.compile(
            r"(?i)\b(?:Invoke-WebRequest|iwr)\b.*"
            r"\b(?:iex|Invoke-Expression)\b"
        ),
        re.compile(r"(?i)\b(?:curl|wget)\b.*\|\s*(?:sh|bash|zsh)\b"),
    )

    _RISK_MAP = {
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

    def __init__(
        self,
        permission_manager: PermissionManager,
        config: SecurityPolicyConfig | None = None,
        rules: Iterable[SecurityRule] | None = None,
    ) -> None:
        if permission_manager is None:
            raise ValueError("PermissionManager is required.")

        self._permissions = permission_manager
        self._config = config or SecurityPolicyConfig()

        self._lock = threading.RLock()

        supplied_rules = (
            list(rules)
            if rules is not None
            else self._default_rules()
        )

        self._rules = supplied_rules
        self._validate_rules()

    @property
    def config(self) -> SecurityPolicyConfig:
        return self._config

    @property
    def rules(self) -> tuple[SecurityRule, ...]:
        with self._lock:
            return tuple(self._rules)

    def add_rule(self, rule: SecurityRule) -> None:
        """Add a rule without allowing duplicate names."""

        if not isinstance(rule, SecurityRule):
            raise TypeError("rule must be a SecurityRule.")

        with self._lock:
            if any(item.name == rule.name for item in self._rules):
                raise ValueError(
                    f"Security rule already exists: {rule.name}"
                )

            self._rules.append(rule)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name."""

        with self._lock:
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

        if not isinstance(operation, OperationType):
            raise TypeError("operation must be an OperationType.")

        if not isinstance(subject, str) or not subject.strip():
            return self._result(
                operation,
                RiskLevel.CRITICAL,
                PermissionDecision.deny("Invalid permission subject."),
            )

        if not isinstance(resource, str) or not resource.strip():
            return self._result(
                operation,
                RiskLevel.CRITICAL,
                PermissionDecision.deny("Invalid resource."),
            )

        normalized_resource = resource.strip()

        effective_workspace = (
            Path(workspace).expanduser().resolve(strict=False)
            if workspace is not None
            else self._config.workspace
        )

        if command is not None:
            inspection = self.inspect_command(command)

            if inspection is not None:
                risk, reason = inspection

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

        matched_rule = self._find_rule(
            operation,
            normalized_resource,
        )

        if matched_rule is not None:
            if matched_rule.action == PermissionAction.DENY:
                reason = (
                    f"Blocked by security rule: {matched_rule.name}"
                )

                return self._result(
                    operation,
                    matched_rule.risk,
                    PermissionDecision.deny(reason),
                    matched_rule.name,
                )

            if matched_rule.action == PermissionAction.ASK:
                reason = (
                    f"Approval required by security rule: "
                    f"{matched_rule.name}"
                )

                return self._result(
                    operation,
                    matched_rule.risk,
                    PermissionDecision.ask(reason),
                    matched_rule.name,
                )

        risk = (
            matched_rule.risk
            if matched_rule is not None
            else self._infer_risk(operation)
        )

        restriction = self._check_config_restrictions(
            operation,
            risk,
        )

        if restriction is not None:
            return self._result(
                operation,
                risk,
                restriction,
                matched_rule.name if matched_rule else None,
            )

        permission_level = self._required_permission(operation)

        try:
            decision = self._permissions.check(
                PermissionRequest(
                    subject=subject,
                    resource=normalized_resource,
                    action=permission_level,
                    workspace=effective_workspace,
                    risk=risk,
                )
            )
        except (ValueError, TypeError) as exc:
            return self._result(
                operation,
                RiskLevel.CRITICAL,
                PermissionDecision.deny(
                    f"Invalid permission request: {exc}"
                ),
            )

        warnings: list[str] = []

        if (
            decision.action == PermissionAction.DENY
            and self._config.mode == PolicyMode.PERMISSIVE
        ):
            warnings.append(
                "Permissive mode never overrides an explicit permission denial."
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
        """Inspect shell commands without executing them.

        This is heuristic inspection, not a security sandbox.
        """

        if not isinstance(command, str) or not command.strip():
            return (
                RiskLevel.HIGH,
                "Empty or invalid terminal commands are not permitted.",
            )

        if len(command) > self._config.max_command_length:
            return (
                RiskLevel.HIGH,
                "Command exceeds the configured length limit.",
            )

        normalized = command.strip()

        # Reject control characters and multiline shell input.
        if any(ord(char) < 32 and char not in "\t" for char in normalized):
            return (
                RiskLevel.HIGH,
                "Control characters in terminal commands are not permitted.",
            )

        # Inspect known dangerous command patterns.
        for pattern in self._DANGEROUS_PATTERNS:
            if pattern.search(normalized):
                return (
                    RiskLevel.CRITICAL,
                    "Command matches a blocked dangerous-operation pattern.",
                )

        # Detect destructive commands even when nested in shell arguments.
        destructive_pattern = re.compile(
            r"(?i)(?<![\w.-])(?:"
            + "|".join(
                re.escape(item)
                for item in sorted(
                    self._DESTRUCTIVE_COMMANDS,
                    key=len,
                    reverse=True,
                )
            )
            + r")(?![\w.-])"
        )

        if destructive_pattern.search(normalized):
            return (
                RiskLevel.CRITICAL,
                "Nested destructive command detected.",
            )

        # PowerShell encoded commands are opaque to reliable static inspection.
        if re.search(
            r"(?i)(?:^|\s)-(?:encodedcommand|enc|e)(?:\s|$)",
            normalized,
        ):
            return (
                RiskLevel.CRITICAL,
                "Encoded shell commands are not permitted.",
            )

        # Shell wrappers can hide nested commands and expansions.
        # Inspect their arguments conservatively.
        try:
            tokens = shlex.split(normalized, posix=False)
        except ValueError:
            return (
                RiskLevel.HIGH,
                "Command could not be safely parsed.",
            )

        if not tokens:
            return (
                RiskLevel.HIGH,
                "Command contains no executable.",
            )

        executable = self._executable_name(tokens[0])

        blocked = set(self._config.blocked_commands)

        if executable in blocked:
            return (
                RiskLevel.CRITICAL,
                f"Executable is blocked by security configuration: {executable}",
            )

        if executable in self._SHELL_EXECUTABLES:
            return self._inspect_shell_wrapper(
                executable,
                tokens,
                normalized,
            )

        # Reject shell operators conservatively.
        if self._SHELL_META.search(normalized):
            return (
                RiskLevel.HIGH,
                "Shell operators require separately approved execution.",
            )

        return None

    @staticmethod
    def _executable_name(value: str) -> str:
        """Normalize an executable name across Windows and POSIX."""

        cleaned = value.strip().strip('"').strip("'")
        return cleaned.replace("\\", "/").rsplit("/", 1)[-1].casefold()

    def _inspect_shell_wrapper(
        self,
        executable: str,
        tokens: list[str],
        original: str,
    ) -> tuple[RiskLevel, str] | None:
        """Inspect nested commands passed to shell interpreters."""

        if executable in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
            command_flags = {
                "-command",
                "-c",
                "/c",
            }

            for index, token in enumerate(tokens[1:], start=1):
                lowered = token.casefold()

                if lowered in command_flags:
                    if index + 1 >= len(tokens):
                        return (
                            RiskLevel.HIGH,
                            "PowerShell command argument is missing.",
                        )

                    nested = tokens[index + 1].strip('"').strip("'")
                    result = self.inspect_command(nested)

                    if result is not None:
                        return result

                    # PowerShell is an interpreter. Its execution semantics
                    # cannot be completely established using token parsing.
                    return (
                        RiskLevel.HIGH,
                        "PowerShell execution requires explicit approval.",
                    )

            return (
                RiskLevel.HIGH,
                "PowerShell interpreter execution requires explicit approval.",
            )

        if executable in {"cmd", "cmd.exe"}:
            for index, token in enumerate(tokens[1:], start=1):
                if token.casefold() in {"/c", "/k"}:
                    if index + 1 >= len(tokens):
                        return (
                            RiskLevel.HIGH,
                            "CMD command argument is missing.",
                        )

                    nested = tokens[index + 1].strip('"').strip("'")
                    result = self.inspect_command(nested)

                    if result is not None:
                        return result

                    return (
                        RiskLevel.HIGH,
                        "CMD shell execution requires explicit approval.",
                    )

            return (
                RiskLevel.HIGH,
                "CMD interpreter execution requires explicit approval.",
            )

        # Bash, sh, zsh, and WSL can execute arbitrary scripts.
        return (
            RiskLevel.HIGH,
            "POSIX shell execution requires explicit approval.",
        )

    def _inspect_protected_path(
        self,
        resource: str,
        workspace: Path | None,
    ) -> str | None:
        """Detect protected paths and workspace traversal."""

        try:
            candidate = Path(resource).expanduser()

            if not candidate.is_absolute():
                if workspace is not None:
                    candidate = workspace / candidate

            resolved = candidate.resolve(strict=False)

            if workspace is not None:
                try:
                    relative = resolved.relative_to(workspace)
                except ValueError:
                    return (
                        "Resource is outside the authorized workspace."
                    )
            else:
                relative = resolved

            path_parts = tuple(
                part.casefold()
                for part in relative.parts
            )

            for protected in self._config.protected_paths:
                pattern = protected.casefold()

                if any(
                    fnmatch.fnmatchcase(part, pattern)
                    for part in path_parts
                ):
                    return (
                        f"Access to protected path is blocked: {protected}"
                    )

            return None

        except (OSError, RuntimeError, ValueError):
            return "Resource path could not be safely resolved."

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

        if self._config.mode == PolicyMode.STRICT:
            if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
                return PermissionDecision.ask(
                    "High-risk operation requires approval in strict mode."
                )

        if (
            self._config.mode == PolicyMode.BALANCED
            and risk == RiskLevel.CRITICAL
        ):
            return PermissionDecision.ask(
                "Critical-risk operation requires approval in balanced mode."
            )

        # PERMISSIVE mode still respects explicit permissions, hard blocks,
        # protected paths, and mandatory configuration restrictions.
        return None

    def _find_rule(
        self,
        operation: OperationType,
        resource: str,
    ) -> SecurityRule | None:
        """Find the first matching enabled rule."""

        with self._lock:
            rules = tuple(self._rules)

        normalized = resource.replace("\\", "/")

        for rule in rules:
            if not rule.enabled or rule.operation != operation:
                continue

            if any(
                fnmatch.fnmatchcase(normalized, pattern.replace("\\", "/"))
                for pattern in rule.resource_patterns
            ):
                return rule

        return None

    @staticmethod
    def _required_permission(
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
        """Infer baseline operation risk."""

        return self._RISK_MAP[operation]

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
        """Validate configured rule uniqueness and types."""

        names: list[str] = []

        for rule in self._rules:
            if not isinstance(rule, SecurityRule):
                raise TypeError("All policy rules must be SecurityRule objects.")

            names.append(rule.name)

        if len(names) != len(set(names)):
            raise ValueError("Security rule names must be unique.")
