
"""Cross-platform shell command preparation for FORGEX."""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from forgex.runtime.adapters import RuntimeAdapter, RuntimeCommand


class ShellType(StrEnum):
    """Supported interactive shell types."""

    POWERSHELL = "powershell"
    CMD = "cmd"
    BASH = "bash"
    ZSH = "zsh"
    SH = "sh"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ShellCommand:
    """A prepared shell invocation."""

    shell_type: ShellType
    command: RuntimeCommand
    original_script: str

    @property
    def argv(self) -> list[str]:
        return self.command.argv


class ShellManager:
    """Prepares shell commands without executing them."""

    _SHELL_ALIASES = {
        "powershell": ShellType.POWERSHELL,
        "powershell.exe": ShellType.POWERSHELL,
        "pwsh": ShellType.POWERSHELL,
        "pwsh.exe": ShellType.POWERSHELL,
        "cmd": ShellType.CMD,
        "cmd.exe": ShellType.CMD,
        "bash": ShellType.BASH,
        "zsh": ShellType.ZSH,
        "sh": ShellType.SH,
    }

    def __init__(self, adapter: RuntimeAdapter) -> None:
        self._adapter = adapter

    @property
    def shell_type(self) -> ShellType:
        """Return the detected shell type."""

        shell = self._adapter.default_shell()

        if shell is None:
            return ShellType.UNKNOWN

        return self._identify_shell(shell)

    def prepare(
        self,
        script: str,
        *,
        shell_type: ShellType | None = None,
        cwd: str | Path | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> ShellCommand:
        """Prepare a script for execution by the selected shell.

        This method never executes commands. The caller must inspect the
        script and obtain the required security approval first.
        """

        if not isinstance(script, str) or not script.strip():
            raise ValueError("Shell script cannot be empty.")

        if "\x00" in script:
            raise ValueError("Shell script cannot contain null bytes.")

        selected = shell_type or self.shell_type

        if selected == ShellType.UNKNOWN:
            raise RuntimeError("No supported shell is available.")

        executable = self._resolve_shell(selected)

        arguments = self._build_arguments(selected, script)

        command = self._adapter.build_command(
            executable,
            arguments,
            cwd=cwd,
            extra_environment=extra_environment,
        )

        return ShellCommand(
            shell_type=selected,
            command=command,
            original_script=script,
        )

    def prepare_argv(
        self,
        arguments: Sequence[str],
        *,
        shell_type: ShellType | None = None,
        cwd: str | Path | None = None,
    ) -> ShellCommand:
        """Prepare an argument sequence as a shell script."""

        if not arguments:
            raise ValueError("Shell arguments cannot be empty.")

        if any("\x00" in argument for argument in arguments):
            raise ValueError("Shell arguments cannot contain null bytes.")

        selected = shell_type or self.shell_type

        if selected in {ShellType.POWERSHELL, ShellType.CMD}:
            script = " ".join(
                self._quote_windows_argument(argument)
                for argument in arguments
            )
        else:
            script = shlex.join(arguments)

        return self.prepare(
            script,
            shell_type=selected,
            cwd=cwd,
        )

    def _resolve_shell(self, shell_type: ShellType) -> Path:
        """Resolve the executable for a shell type."""

        candidates = {
            ShellType.POWERSHELL: ("pwsh", "powershell"),
            ShellType.CMD: ("cmd",),
            ShellType.BASH: ("bash",),
            ShellType.ZSH: ("zsh",),
            ShellType.SH: ("sh",),
        }

        for candidate in candidates.get(shell_type, ()):
            resolved = self._adapter.resolve_executable(candidate)

            if resolved is not None:
                return resolved

        raise FileNotFoundError(
            f"Shell executable not found for {shell_type.value}."
        )

    @staticmethod
    def _build_arguments(
        shell_type: ShellType,
        script: str,
    ) -> tuple[str, ...]:
        """Build safe argv boundaries for a shell script."""

        if shell_type == ShellType.POWERSHELL:
            return (
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            )

        if shell_type == ShellType.CMD:
            return ("/d", "/s", "/c", script)

        if shell_type in {
            ShellType.BASH,
            ShellType.ZSH,
            ShellType.SH,
        }:
            return ("-c", script)

        raise ValueError(f"Unsupported shell type: {shell_type.value}")

    @staticmethod
    def _quote_windows_argument(argument: str) -> str:
        """Quote an argument for PowerShell or CMD script construction."""

        if not argument:
            return '""'

        if not any(character.isspace() or character in '"&|<>^' for character in argument):
            return argument

        # This produces a PowerShell single-quoted literal.
        # CMD requires separate escaping and should not be used for
        # untrusted arguments without a dedicated Windows quoting layer.
        return "'" + argument.replace("'", "''") + "'"

    def _identify_shell(self, executable: Path) -> ShellType:
        """Identify a shell from its executable name."""

        name = executable.name.lower()
        return self._SHELL_ALIASES.get(name, ShellType.UNKNOWN)


__all__ = [
    "ShellType",
    "ShellCommand",
    "ShellManager",
]
