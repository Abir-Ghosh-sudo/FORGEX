
"""Adapter between RuntimeManager commands and ProcessSupervisor."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from forgex.runtime.adapters import RuntimeCommand
from forgex.runtime.supervisor import (
    ProcessSupervisor,
    SupervisedProcessResult,
)


class SupervisorAdapter:
    """Execute RuntimeCommand instances through ProcessSupervisor."""

    def __init__(self, supervisor: ProcessSupervisor) -> None:
        if not isinstance(supervisor, ProcessSupervisor):
            raise TypeError("supervisor must be a ProcessSupervisor.")

        self.supervisor = supervisor

    async def execute(
        self,
        command: RuntimeCommand,
        *,
        timeout: float | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> SupervisedProcessResult:
        """Execute a prepared runtime command under supervision."""

        if not isinstance(command, RuntimeCommand):
            raise TypeError("command must be a RuntimeCommand.")

        if not command.executable.is_absolute():
            raise ValueError("Executable path must be absolute.")

        argv = command.argv

        if not argv:
            raise ValueError("Runtime command has no executable.")

        working_directory = Path(command.working_directory)

        if not working_directory.is_dir():
            raise ValueError("Command working directory does not exist.")

        merged_environment = dict(command.environment)

        if environment:
            merged_environment.update(environment)

        for key, value in merged_environment.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("Environment variables must be strings.")

            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError("Invalid environment variable.")

        return await self.supervisor.execute(
            argv,
            cwd=working_directory,
            env=merged_environment,
            timeout=timeout,
        )

    async def shutdown(self) -> None:
        """Shut down the underlying supervisor."""
        await self.supervisor.shutdown()
