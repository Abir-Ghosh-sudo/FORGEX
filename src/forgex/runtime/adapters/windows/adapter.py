
"""Windows-specific runtime adapter for FORGEX."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Sequence

from forgex.runtime.adapters import RuntimeAdapter, RuntimeCommand
from forgex.runtime.environment import RuntimeEnvironment


class WindowsRuntimeAdapter(RuntimeAdapter):
    """Provides Windows-specific runtime and command preparation."""

    def __init__(self, environment: RuntimeEnvironment) -> None:
        if not environment.is_windows:
            raise ValueError(
                "WindowsRuntimeAdapter requires a Windows environment."
            )

        super().__init__(environment)

    def resolve_executable(self, name: str) -> Path | None:
        """Resolve an executable using Windows PATH and PATHEXT rules."""

        if not name or not name.strip():
            raise ValueError("Executable name cannot be empty.")

        expanded = Path(name).expanduser()

        # Explicit paths should be checked directly.
        if expanded.is_absolute() or "\\" in name or "/" in name:
            candidate = expanded.resolve(strict=False)

            if candidate.is_file():
                return candidate

            return None

        discovered = shutil.which(name)

        if discovered is None:
            return None

        return Path(discovered).resolve(strict=False)

    def normalize_path(self, path: str | Path) -> Path:
        """Normalize a Windows filesystem path."""

        if isinstance(path, str) and not path.strip():
            raise ValueError("Path cannot be empty.")

        return Path(path).expanduser().resolve(strict=False)

    def default_shell(self) -> Path | None:
        """Return the preferred Windows shell."""

        detected = self.environment.shell_executable

        if detected is not None and detected.is_file():
            return detected

        candidates = (
            "pwsh.exe",
            "powershell.exe",
            "cmd.exe",
        )

        for candidate in candidates:
            resolved = self.resolve_executable(candidate)

            if resolved is not None:
                return resolved

        return None

    def build_command(
        self,
        executable: str | Path,
        arguments: Sequence[str],
        *,
        cwd: str | Path | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> RuntimeCommand:
        """Build a Windows command without executing it."""

        executable_name = str(executable)

        if not executable_name.strip():
            raise ValueError("Executable cannot be empty.")

        resolved = self.resolve_executable(executable_name)

        if resolved is None:
            raise FileNotFoundError(
                f"Executable could not be resolved: {executable_name}"
            )

        normalized_arguments = tuple(str(argument) for argument in arguments)

        if any("\x00" in argument for argument in normalized_arguments):
            raise ValueError("Command arguments cannot contain null bytes.")

        working_directory = self.normalize_path(
            cwd if cwd is not None else self.environment.working_directory
        )

        if not working_directory.is_dir():
            raise NotADirectoryError(
                f"Working directory does not exist: {working_directory}"
            )

        command_environment = dict(os.environ)

        if extra_environment:
            for key, value in extra_environment.items():
                if not key or "=" in key or "\x00" in key:
                    raise ValueError(f"Invalid environment variable name: {key!r}")

                if "\x00" in value:
                    raise ValueError(
                        f"Environment variable {key!r} contains a null byte."
                    )

                # Windows environment variable names are case-insensitive.
                existing_key = next(
                    (
                        current
                        for current in command_environment
                        if current.casefold() == key.casefold()
                    ),
                    key,
                )

                command_environment[existing_key] = value

        return RuntimeCommand(
            executable=resolved,
            arguments=normalized_arguments,
            working_directory=working_directory,
            environment=command_environment,
        )
