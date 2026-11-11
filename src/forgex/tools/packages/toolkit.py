"""Unified package management toolkit for FORGEX."""

from __future__ import annotations

from pathlib import Path

from forgex.runtime.supervisor import ProcessSupervisor
from forgex.tools.packages.commands import PackageCommandBuilder
from forgex.tools.packages.detector import (
    PackageDetectionError,
    PackageManagerDetector,
)
from forgex.tools.packages.executor import (
    PackageExecutionError,
    PackageExecutor,
)
from forgex.tools.packages.models import (
    InstalledPackage,
    PackageManager,
    PackageOperation,
    PackageRequest,
    PackageResult,
    PackageSpec,
)
from forgex.tools.packages.parser import (
    PackageOutputParser,
    PackageParseError,
)


class PackageToolkitError(RuntimeError):
    """Unified package toolkit error."""


class PackageToolkit:
    """High-level API for package management."""

    def __init__(
        self,
        workspace: Path,
        supervisor: ProcessSupervisor,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

        if not self.workspace.is_dir():
            raise PackageToolkitError(
                f"Workspace does not exist: {self.workspace}"
            )

        self.detector = PackageManagerDetector()
        self.builder = PackageCommandBuilder()
        self.executor = PackageExecutor(
            supervisor,
            detector=self.detector,
            builder=self.builder,
        )
        self.parser = PackageOutputParser()

    def detect_manager(
        self,
        preferred: PackageManager = PackageManager.AUTO,
    ):
        try:
            return self.detector.detect(
                self.workspace,
                preferred,
            )
        except PackageDetectionError as exc:
            raise PackageToolkitError(str(exc)) from exc

    async def execute(
        self,
        operation: PackageOperation,
        packages: tuple[PackageSpec, ...] = (),
        *,
        manager: PackageManager = PackageManager.AUTO,
        timeout_seconds: float = 300.0,
        dry_run: bool = False,
        environment: dict[str, str] | None = None,
    ) -> PackageResult:
        request = PackageRequest(
            workspace=self.workspace,
            operation=operation,
            manager=manager,
            packages=packages,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
            environment=environment or {},
        )

        try:
            return await self.executor.execute(request)
        except PackageExecutionError as exc:
            raise PackageToolkitError(str(exc)) from exc

    async def install(
        self,
        *packages: PackageSpec,
        manager: PackageManager = PackageManager.AUTO,
        dry_run: bool = False,
    ) -> PackageResult:
        return await self.execute(
            PackageOperation.INSTALL,
            tuple(packages),
            manager=manager,
            dry_run=dry_run,
        )

    async def uninstall(
        self,
        *packages: PackageSpec,
        manager: PackageManager = PackageManager.AUTO,
    ) -> PackageResult:
        return await self.execute(
            PackageOperation.UNINSTALL,
            tuple(packages),
            manager=manager,
        )

    async def update(
        self,
        *packages: PackageSpec,
        manager: PackageManager = PackageManager.AUTO,
        dry_run: bool = False,
    ) -> PackageResult:
        return await self.execute(
            PackageOperation.UPDATE,
            tuple(packages),
            manager=manager,
            dry_run=dry_run,
        )

    async def list_packages(
        self,
        manager: PackageManager = PackageManager.AUTO,
    ) -> tuple[InstalledPackage, ...]:
        result = await self.execute(
            PackageOperation.LIST,
            manager=manager,
        )

        if not result.success:
            raise PackageToolkitError(
                result.error or "Unable to list packages."
            )

        return self.parser.parse(
            result.stdout,
            result.manager,
        )

    async def check(
        self,
        manager: PackageManager = PackageManager.AUTO,
    ) -> PackageResult:
        return await self.execute(
            PackageOperation.CHECK,
            manager=manager,
        )

    async def audit(
        self,
        manager: PackageManager = PackageManager.AUTO,
    ) -> PackageResult:
        return await self.execute(
            PackageOperation.AUDIT,
            manager=manager,
        )

    async def freeze(
        self,
        manager: PackageManager = PackageManager.AUTO,
    ) -> PackageResult:
        return await self.execute(
            PackageOperation.FREEZE,
            manager=manager,
        )

    async def info(
        self,
        *packages: PackageSpec,
        manager: PackageManager = PackageManager.AUTO,
    ) -> PackageResult:
        return await self.execute(
            PackageOperation.INFO,
            tuple(packages),
            manager=manager,
        )

    def parse_output(
        self,
        output: str,
        manager: PackageManager,
    ) -> tuple[InstalledPackage, ...]:
        try:
            return self.parser.parse(output, manager)
        except PackageParseError as exc:
            raise PackageToolkitError(str(exc)) from exc