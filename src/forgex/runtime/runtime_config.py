
"""Runtime configuration and validation for FORGEX."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from forgex.runtime.limits import ResourceLimits


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Central configuration for the FORGEX execution runtime."""

    default_timeout: float = 120.0
    shutdown_timeout: float = 10.0
    termination_grace_period: float = 3.0

    max_concurrent_processes: int = 4
    max_output_bytes: int = 1_048_576
    output_chunk_size: int = 8192

    encoding: str = "utf-8"
    inherit_environment: bool = True

    shell_enabled: bool = True
    shell_approval_required: bool = True

    process_tree_termination: bool = True
    capture_stdout: bool = True
    capture_stderr: bool = True

    allowed_environment_variables: tuple[str, ...] = (
        "PATH",
        "HOME",
        "USER",
        "USERNAME",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "WINDIR",
        "VIRTUAL_ENV",
        "PYTHONPATH",
    )

    blocked_environment_variables: tuple[str, ...] = (
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
        "PYTHONINSPECT",
        "PYTHONSTARTUP",
    )

    workspace: Path | None = None

    platform: Literal["auto", "windows", "linux", "macos"] = "auto"

    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.default_timeout <= 0:
            raise ValueError("default_timeout must be positive.")

        if self.shutdown_timeout <= 0:
            raise ValueError("shutdown_timeout must be positive.")

        if self.termination_grace_period < 0:
            raise ValueError(
                "termination_grace_period cannot be negative."
            )

        if self.max_concurrent_processes < 1:
            raise ValueError(
                "max_concurrent_processes must be positive."
            )

        if self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive.")

        if self.output_chunk_size < 1:
            raise ValueError("output_chunk_size must be positive.")

        if self.platform not in {"auto", "windows", "linux", "macos"}:
            raise ValueError("Unsupported runtime platform.")

        if not self.encoding.strip():
            raise ValueError("encoding cannot be empty.")

        if self.workspace is not None:
            workspace = Path(self.workspace).expanduser().resolve()

            if not workspace.exists() or not workspace.is_dir():
                raise ValueError("Configured workspace is invalid.")

            object.__setattr__(self, "workspace", workspace)

        object.__setattr__(
            self,
            "allowed_environment_variables",
            tuple(self.allowed_environment_variables),
        )

        object.__setattr__(
            self,
            "blocked_environment_variables",
            tuple(self.blocked_environment_variables),
        )

        object.__setattr__(self, "metadata", dict(self.metadata))

        if set(self.allowed_environment_variables) & set(
            self.blocked_environment_variables
        ):
            raise ValueError(
                "Environment variables cannot be both allowed and blocked."
            )

    def resource_limits(self) -> ResourceLimits:
        """Create matching process resource limits."""

        return ResourceLimits(
            timeout_seconds=self.default_timeout,
            max_output_bytes=self.max_output_bytes,
            max_concurrent_processes=self.max_concurrent_processes,
        )

    def filter_environment(
        self,
        environment: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Build an environment containing only explicitly allowed keys.

        Blocked variables are rejected even if they appear in the allowlist.
        """

        source = dict(os.environ) if environment is None else dict(environment)

        allowed = set(self.allowed_environment_variables)
        blocked = set(self.blocked_environment_variables)

        filtered: dict[str, str] = {}

        for key, value in source.items():
            normalized_key = key.upper() if os.name == "nt" else key

            normalized_allowed = (
                {item.upper() for item in allowed}
                if os.name == "nt"
                else allowed
            )

            normalized_blocked = (
                {item.upper() for item in blocked}
                if os.name == "nt"
                else blocked
            )

            if normalized_key in normalized_blocked:
                continue

            if normalized_key not in normalized_allowed:
                continue

            if not isinstance(value, str):
                continue

            if "\x00" in key or "\x00" in value or "=" in key:
                continue

            filtered[key] = value

        return filtered


__all__ = ["RuntimeConfig"]
