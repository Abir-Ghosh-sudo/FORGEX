
"""Typed request and result models for FORGEX terminal execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Mapping


class TerminalExecutionStatus(StrEnum):
    """Final state of a terminal execution."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class TerminalRequest:
    """A validated request to execute a terminal program.

    Commands are represented as an argument sequence rather than a shell
    string. This prevents accidental shell interpretation and injection.
    """

    argv: tuple[str, ...]
    working_directory: Path
    timeout_seconds: float = 120.0
    environment: Mapping[str, str] = field(default_factory=dict)
    stdin: str | None = None
    max_output_bytes: int = 1_048_576
    subject: str = "agent"
    session_id: str | None = None

    def __post_init__(self) -> None:
        normalized_argv = tuple(self.argv)
        object.__setattr__(self, "argv", normalized_argv)
        object.__setattr__(
            self,
            "working_directory",
            Path(self.working_directory).expanduser(),
        )
        object.__setattr__(self, "environment", dict(self.environment))

        if not normalized_argv:
            raise ValueError("argv must contain an executable.")

        if any(not isinstance(arg, str) for arg in normalized_argv):
            raise TypeError("Every argv element must be a string.")

        if any("\x00" in arg for arg in normalized_argv):
            raise ValueError("Command arguments cannot contain null bytes.")

        if not normalized_argv[0].strip():
            raise ValueError("Executable cannot be empty.")

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        if self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be greater than zero.")

        if not self.subject.strip():
            raise ValueError("subject cannot be empty.")

        for key, value in self.environment.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("Environment keys and values must be strings.")
            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError(f"Invalid environment variable: {key!r}")

        if self.stdin is not None and not isinstance(self.stdin, str):
            raise TypeError("stdin must be a string or None.")

    @property
    def executable(self) -> str:
        """Return the executable name or path."""
        return self.argv[0]

    @property
    def arguments(self) -> tuple[str, ...]:
        """Return arguments excluding the executable."""
        return self.argv[1:]


@dataclass(frozen=True, slots=True)
class TerminalResult:
    """Immutable result returned after terminal execution."""

    status: TerminalExecutionStatus
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    working_directory: Path
    truncated: bool = False
    process_id: int | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(
            self,
            "working_directory",
            Path(self.working_directory),
        )

        if self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative.")

        if self.status is TerminalExecutionStatus.SUCCESS:
            if self.exit_code != 0:
                raise ValueError("Successful execution must have exit_code 0.")

        if self.status is TerminalExecutionStatus.FAILED:
            if self.exit_code in (None, 0):
                raise ValueError("Failed execution must have a non-zero exit code.")

    @property
    def succeeded(self) -> bool:
        """Whether the command completed successfully."""
        return self.status is TerminalExecutionStatus.SUCCESS

    @property
    def output(self) -> str:
        """Combine stdout and stderr for concise display."""
        if self.stdout and self.stderr:
            return f"{self.stdout}\n{self.stderr}"
        return self.stdout or self.stderr

    def to_dict(self) -> dict[str, object]:
        """Convert the result into a JSON-compatible dictionary."""
        return {
            "status": self.status.value,
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "working_directory": str(self.working_directory),
            "truncated": self.truncated,
            "process_id": self.process_id,
            "error": self.error,
            "succeeded": self.succeeded,
        }
