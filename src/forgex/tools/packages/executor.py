"""Package command execution for FORGEX."""

from __future__ import annotations

import os
import time
from pathlib import Path

from forgex.runtime.supervisor import (
    ProcessSupervisor,
    SupervisedProcessState,
)
from forgex.tools.packages.commands import (
    PackageCommandBuilder,
    PackageCommandError,
)
from forgex.tools.packages.detector import (
    PackageManagerDetector,
)
from forgex.tools.packages.models import (
    PackageManager,
    PackageRequest,
    PackageResult,
    PackageStatus,
)


class PackageExecutionError(RuntimeError):
    """Raised when package command execution fails."""


class PackageExecutor:
    """Execute package operations through ProcessSupervisor."""

    def __init__(
        self,
        supervisor: ProcessSupervisor,
        detector: PackageManagerDetector | None = None,
        builder: PackageCommandBuilder | None = None,
    ) -> None:
        self.supervisor = supervisor
        self.detector = detector or PackageManagerDetector()
        self.builder = builder or PackageCommandBuilder()

    async def execute(self, request: PackageRequest) -> PackageResult:
        workspace = Path(request.workspace).expanduser().resolve()

        if not workspace.is_dir():
            raise PackageExecutionError(
                f"Workspace does not exist: {workspace}"
            )

        started = time.monotonic()
        manager = request.manager

        try:
            if manager == PackageManager.AUTO:
                detected = self.detector.detect(workspace)
                manager = detected.manager

            command = self.builder.build(request, manager)

            if not command:
                raise PackageExecutionError(
                    "Package command cannot be empty."
                )

            if request.dry_run:
                return PackageResult(
                    operation=request.operation,
                    manager=manager,
                    status=PackageStatus.SUCCESS,
                    command=command,
                    duration_seconds=0.0,
                    stdout="Dry run: command was not executed.",
                    dry_run=True,
                )

            environment = os.environ.copy()
            environment.update(request.environment)

            result = await self.supervisor.execute(
                list(command),
                cwd=workspace,
                env=environment,
                timeout=request.timeout_seconds,
            )

            status = self._map_status(
                result.state,
                result.return_code,
            )

            output = result.output

            return PackageResult(
                operation=request.operation,
                manager=manager,
                status=status,
                command=command,
                exit_code=result.return_code,
                stdout=self._decode(output.stdout),
                stderr=self._decode(output.stderr),
                duration_seconds=time.monotonic() - started,
                error=(
                    self._decode(output.stderr).strip()
                    if status != PackageStatus.SUCCESS
                    else None
                ),
            )

        except PackageCommandError as exc:
            raise PackageExecutionError(str(exc)) from exc

        except PackageExecutionError:
            raise

        except Exception as exc:
            raise PackageExecutionError(
                f"Package operation failed: {exc}"
            ) from exc

    @staticmethod
    def _decode(value: bytes | str | None) -> str:
        if value is None:
            return ""

        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")

        return str(value)

    @staticmethod
    def _map_status(
        state: SupervisedProcessState,
        return_code: int,
    ) -> PackageStatus:
        if state == SupervisedProcessState.COMPLETED:
            return (
                PackageStatus.SUCCESS
                if return_code == 0
                else PackageStatus.FAILED
            )

        if state == SupervisedProcessState.TIMED_OUT:
            return PackageStatus.TIMEOUT

        if state == SupervisedProcessState.CANCELLED:
            return PackageStatus.ERROR

        return PackageStatus.ERROR