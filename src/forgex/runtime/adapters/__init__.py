"""Cross-platform runtime adapter interfaces and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from forgex.runtime.environment import RuntimeEnvironment


@dataclass(frozen=True, slots=True)
class RuntimeCommand:
    """A normalized command prepared for platform execution."""

    executable: Path
    arguments: tuple[str, ...]
    working_directory: Path
    environment: dict[str, str]

    def __post_init__(self) -> None:
        if not self.executable:
            raise ValueError("Command executable cannot be empty.")

        if not self.working_directory:
            raise ValueError("Working directory cannot be empty.")

        object.__setattr__(
            self,
            "executable",
            Path(self.executable).expanduser().resolve(strict=False),
        )
        object.__setattr__(
            self,
            "working_directory",
            Path(self.working_directory).expanduser().resolve(strict=False),
        )
        object.__setattr__(self, "arguments", tuple(self.arguments))
        object.__setattr__(self, "environment", dict(self.environment))

    @property
    def argv(self) -> list[str]:
        """Return the executable and arguments as an argv list."""
        return [str(self.executable), *self.arguments]


class RuntimeAdapter(ABC):
    """Abstract interface for operating-system-specific runtime behavior."""

    def __init__(self, environment: RuntimeEnvironment) -> None:
        self._environment = environment

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    @abstractmethod
    def resolve_executable(self, name: str) -> Path | None:
        """Resolve an executable using the host platform's conventions."""

    @abstractmethod
    def normalize_path(self, path: str | Path) -> Path:
        """Normalize a filesystem path for the current platform."""

    @abstractmethod
    def default_shell(self) -> Path | None:
        """Return the preferred shell executable."""

    @abstractmethod
    def build_command(
        self,
        executable: str | Path,
        arguments: Sequence[str],
        *,
        cwd: str | Path | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> RuntimeCommand:
        """Build a normalized command without executing it."""


def create_runtime_adapter(
    environment: RuntimeEnvironment | None = None,
) -> RuntimeAdapter:
    """Create the runtime adapter matching the detected operating system."""

    detected = environment or RuntimeEnvironment.detect()

    if detected.is_windows:
        from forgex.runtime.adapters.windows.adapter import WindowsRuntimeAdapter

        return WindowsRuntimeAdapter(detected)

    if detected.is_linux or detected.is_macos:
        from forgex.runtime.adapters.linux.adapter import LinuxRuntimeAdapter

        return LinuxRuntimeAdapter(detected)

    raise RuntimeError(f"Unsupported operating system: {detected.operating_system}")


__all__ = [
    "RuntimeAdapter",
    "RuntimeCommand",
    "create_runtime_adapter",
]
