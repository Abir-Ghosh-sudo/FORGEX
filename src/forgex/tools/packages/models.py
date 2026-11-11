"""Data models for FORGEX package management."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(UTC)


class PackageManager(StrEnum):
    AUTO = "auto"
    PIP = "pip"
    UV = "uv"
    POETRY = "poetry"
    NPM = "npm"
    PNPM = "pnpm"
    YARN = "yarn"
    BUN = "bun"
    CARGO = "cargo"
    GO = "go"
    DOTNET = "dotnet"


class PackageOperation(StrEnum):
    LIST = "list"
    INSTALL = "install"
    UNINSTALL = "uninstall"
    UPDATE = "update"
    CHECK = "check"
    FREEZE = "freeze"
    AUDIT = "audit"
    INFO = "info"


class PackageStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    DENIED = "denied"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PackageSpec:
    name: str
    version: str | None = None
    extras: tuple[str, ...] = ()
    editable: bool = False
    source: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Package name cannot be empty")

        if self.name.startswith("-") or "\x00" in self.name:
            raise ValueError("Invalid package name")

        if self.version is not None and (
            not self.version.strip() or "\x00" in self.version
        ):
            raise ValueError("Invalid package version")

        if any(not item or "\x00" in item for item in self.extras):
            raise ValueError("Invalid package extras")

        if self.source is not None and (not self.source.strip() or "\x00" in self.source):
            raise ValueError("Invalid package source")


@dataclass(frozen=True, slots=True)
class InstalledPackage:
    name: str
    version: str
    manager: PackageManager
    description: str | None = None
    location: str | None = None
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PackageRequest:
    workspace: Path
    operation: PackageOperation
    manager: PackageManager = PackageManager.AUTO
    packages: tuple[PackageSpec, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = 300.0
    allow_prerelease: bool = False
    dry_run: bool = False
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", Path(self.workspace))

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

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

        if self.operation in (
            PackageOperation.INSTALL,
            PackageOperation.UNINSTALL,
            PackageOperation.UPDATE,
        ) and not self.packages:
            raise ValueError(
                f"{self.operation.value} requires at least one package"
            )


@dataclass(frozen=True, slots=True)
class PackageResult:
    operation: PackageOperation
    manager: PackageManager
    status: PackageStatus
    packages: tuple[InstalledPackage, ...] = ()
    command: tuple[str, ...] = ()
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    error: str | None = None
    dry_run: bool = False
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")

    @property
    def success(self) -> bool:
        return self.status == PackageStatus.SUCCESS

    @property
    def package_count(self) -> int:
        return len(self.packages)