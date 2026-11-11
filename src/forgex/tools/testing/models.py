"""Data models for FORGEX testing tools."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


class TestFramework(StrEnum):
    AUTO = "auto"
    PYTEST = "pytest"
    UNITTEST = "unittest"
    NODE = "node"
    JEST = "jest"
    VITEST = "vitest"
    CARGO = "cargo"
    GO = "go"
    DOTNET = "dotnet"
    CUSTOM = "custom"


class TestStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    NOT_RUN = "not_run"


@dataclass(frozen=True, slots=True)
class TestRequest:
    """Configuration for a test execution."""

    workspace: Path
    framework: TestFramework = TestFramework.AUTO
    target: str | None = None
    test_paths: tuple[str, ...] = ()
    markers: tuple[str, ...] = ()
    extra_args: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = 600.0
    max_output_bytes: int = 2_000_000
    coverage: bool = False
    fail_fast: bool = False
    parallel: bool = False
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", Path(self.workspace))

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")

        for name, values in (
            ("test_paths", self.test_paths),
            ("markers", self.markers),
            ("extra_args", self.extra_args),
        ):
            if not all(isinstance(value, str) and value for value in values):
                raise ValueError(f"{name} must contain non-empty strings")

        if self.target is not None and not self.target.strip():
            raise ValueError("target cannot be empty")

        for key, value in self.environment.items():
            if (
                not isinstance(key, str)
                or not key
                or "=" in key
                or "\x00" in key
                or not isinstance(value, str)
                or "\x00" in value
            ):
                raise ValueError("Invalid environment variable")


@dataclass(frozen=True, slots=True)
class TestCaseResult:
    name: str
    status: TestStatus
    duration_seconds: float = 0.0
    file_path: str | None = None
    line_number: int | None = None
    message: str | None = None
    traceback: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Test case name cannot be empty")
        if self.duration_seconds < 0:
            raise ValueError("Test duration cannot be negative")
        if self.line_number is not None and self.line_number < 1:
            raise ValueError("line_number must be positive")


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    line_percent: float | None = None
    branch_percent: float | None = None
    statements: int = 0
    statements_covered: int = 0
    branches: int = 0
    branches_covered: int = 0
    report_path: Path | None = None

    def __post_init__(self) -> None:
        for name in ("line_percent", "branch_percent"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")

        for name in (
            "statements",
            "statements_covered",
            "branches",
            "branches_covered",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")

        if self.statements_covered > self.statements:
            raise ValueError("Covered statements cannot exceed total statements")

        if self.branches_covered > self.branches:
            raise ValueError("Covered branches cannot exceed total branches")

        if self.report_path is not None:
            object.__setattr__(self, "report_path", Path(self.report_path))


@dataclass(frozen=True, slots=True)
class TestRunResult:
    run_id: str
    framework: TestFramework
    status: TestStatus
    workspace: Path
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    cases: tuple[TestCaseResult, ...] = ()
    coverage: CoverageSummary | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    output_truncated: bool = False
    command: tuple[str, ...] = ()
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id cannot be empty")

        object.__setattr__(self, "workspace", Path(self.workspace))

        if self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")

        if self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")

    @property
    def passed(self) -> int:
        return sum(case.status == TestStatus.PASSED for case in self.cases)

    @property
    def failed(self) -> int:
        return sum(case.status == TestStatus.FAILED for case in self.cases)

    @property
    def skipped(self) -> int:
        return sum(case.status == TestStatus.SKIPPED for case in self.cases)

    @property
    def errors(self) -> int:
        return sum(case.status == TestStatus.ERROR for case in self.cases)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def success(self) -> bool:
        return self.status == TestStatus.PASSED and self.exit_code in (None, 0)
