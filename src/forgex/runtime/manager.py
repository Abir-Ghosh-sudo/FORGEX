
"""Central runtime manager for FORGEX."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from forgex.runtime.adapters import (
    RuntimeAdapter,
    RuntimeCommand,
    create_runtime_adapter,
)
from forgex.runtime.environment import RuntimeEnvironment
from forgex.runtime.process import (
    ProcessManager,
    ProcessResult,
    ProcessSpec,
)
from forgex.runtime.shell import (
    ShellCommand,
    ShellManager,
    ShellType,
)


class RuntimeManager:
    """Coordinates platform adapters, shell preparation and processes.

    This manager does not grant permissions automatically. Callers must
    perform security checks and obtain required approval before execution.
    """

    def __init__(
        self,
        environment: RuntimeEnvironment | None = None,
        *,
        adapter: RuntimeAdapter | None = None,
        process_manager: ProcessManager | None = None,
    ) -> None:
        self._environment = environment or RuntimeEnvironment.detect()
        self._adapter = adapter or create_runtime_adapter(self._environment)

        if self._adapter.environment != self._environment:
            raise ValueError(
                "Runtime adapter environment does not match runtime manager."
            )

        self._process_manager = process_manager or ProcessManager()
        self._shell_manager = ShellManager(self._adapter)

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    @property
    def adapter(self) -> RuntimeAdapter:
        return self._adapter

    @property
    def process_manager(self) -> ProcessManager:
        return self._process_manager

    @property
    def shell_manager(self) -> ShellManager:
        return self._shell_manager

    @property
    def shell_type(self) -> ShellType:
        return self._shell_manager.shell_type

    def resolve_executable(self, name: str) -> Path | None:
        return self._adapter.resolve_executable(name)

    def normalize_path(self, path: str | Path) -> Path:
        return self._adapter.normalize_path(path)

    def build_command(
        self,
        executable: str | Path,
        arguments: Sequence[str] = (),
        *,
        cwd: str | Path | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> RuntimeCommand:
        """Build a direct executable command without running it."""

        return self._adapter.build_command(
            executable,
            arguments,
            cwd=cwd,
            extra_environment=extra_environment,
        )

    def prepare_shell_command(
        self,
        script: str,
        *,
        shell_type: ShellType | None = None,
        cwd: str | Path | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> ShellCommand:
        """Prepare a shell script without executing it."""

        return self._shell_manager.prepare(
            script,
            shell_type=shell_type,
            cwd=cwd,
            extra_environment=extra_environment,
        )

    async def execute(
        self,
        command: RuntimeCommand,
        *,
        timeout_seconds: float | None = 300.0,
        input_text: str | None = None,
        max_output_bytes: int = 10 * 1024 * 1024,
    ) -> ProcessResult:
        """Execute a prepared direct command.

        Security authorization is the caller's responsibility.
        """

        spec = ProcessSpec(
            command=command,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )

        return await self._process_manager.execute(
            spec,
            input_text=input_text,
        )

    async def execute_shell(
        self,
        shell_command: ShellCommand,
        *,
        timeout_seconds: float | None = 300.0,
        input_text: str | None = None,
        max_output_bytes: int = 10 * 1024 * 1024,
    ) -> ProcessResult:
        """Execute a previously prepared shell command.

        The caller must inspect the original script and complete the
        permission and approval workflow before calling this method.
        """

        return await self.execute(
            shell_command.command,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
            max_output_bytes=max_output_bytes,
        )

    async def terminate_process(
        self,
        pid: int,
        *,
        force: bool = False,
    ) -> bool:
        return await self._process_manager.terminate(
            pid,
            force=force,
        )

    async def shutdown(self, *, force: bool = False) -> int:
        """Terminate all processes managed by this runtime."""

        return await self._process_manager.terminate_all(force=force)


__all__ = ["RuntimeManager"]
