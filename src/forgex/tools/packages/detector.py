"""Package manager and project ecosystem detection."""

from __future__ import annotations

import json
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.packages.models import PackageManager


class PackageDetectionError(RuntimeError):
    """Raised when package manager detection fails."""


@dataclass(frozen=True, slots=True)
class PackageManagerInfo:
    manager: PackageManager
    project_file: str | None
    executable: str | None
    confidence: float = 1.0

    @property
    def available(self) -> bool:
        return bool(
            self.executable
            and shutil.which(self.executable)
        )


class PackageManagerDetector:
    """Detect package managers using project configuration."""

    def detect(
        self,
        workspace: Path,
        preferred: PackageManager = PackageManager.AUTO,
    ) -> PackageManagerInfo:
        root = Path(workspace).expanduser().resolve()

        if not root.is_dir():
            raise PackageDetectionError(
                f"Workspace does not exist: {root}"
            )

        if preferred != PackageManager.AUTO:
            return self._preferred(root, preferred)

        checks = (
            self._python,
            self._node,
            self._rust,
            self._go,
            self._dotnet,
        )

        for check in checks:
            result = check(root)
            if result:
                return result

        raise PackageDetectionError(
            f"No supported package manager detected in {root}"
        )

    def _preferred(
        self,
        root: Path,
        manager: PackageManager,
    ) -> PackageManagerInfo:
        executables = {
            PackageManager.PIP: "pip",
            PackageManager.UV: "uv",
            PackageManager.POETRY: "poetry",
            PackageManager.NPM: "npm",
            PackageManager.PNPM: "pnpm",
            PackageManager.YARN: "yarn",
            PackageManager.BUN: "bun",
            PackageManager.CARGO: "cargo",
            PackageManager.GO: "go",
            PackageManager.DOTNET: "dotnet",
        }

        executable = executables.get(manager)

        if not executable:
            raise PackageDetectionError(
                f"Unsupported package manager: {manager}"
            )

        return PackageManagerInfo(
            manager=manager,
            project_file=None,
            executable=executable,
        )

    def _python(self, root: Path) -> PackageManagerInfo | None:
        uv_lock = root / "uv.lock"
        poetry_lock = root / "poetry.lock"
        pyproject = root / "pyproject.toml"
        requirements = root / "requirements.txt"

        if uv_lock.is_file():
            return PackageManagerInfo(
                PackageManager.UV, "uv.lock", "uv"
            )

        if poetry_lock.is_file():
            return PackageManagerInfo(
                PackageManager.POETRY, "poetry.lock", "poetry"
            )

        if pyproject.is_file():
            try:
                with pyproject.open("rb") as file:
                    data = tomllib.load(file)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise PackageDetectionError(
                    f"Invalid pyproject.toml: {exc}"
                ) from exc

            if "tool" in data and "poetry" in data["tool"]:
                return PackageManagerInfo(
                    PackageManager.POETRY,
                    "pyproject.toml",
                    "poetry",
                )

            return PackageManagerInfo(
                PackageManager.PIP,
                "pyproject.toml",
                "pip",
                confidence=0.8,
            )

        if requirements.is_file():
            return PackageManagerInfo(
                PackageManager.PIP,
                "requirements.txt",
                "pip",
            )

        return None

    def _node(self, root: Path) -> PackageManagerInfo | None:
        package_file = root / "package.json"

        if not package_file.is_file():
            return None

        try:
            data = json.loads(
                package_file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise PackageDetectionError(
                f"Invalid package.json: {exc}"
            ) from exc

        package_manager = data.get("packageManager", "")

        if package_manager.startswith("pnpm@"):
            manager = PackageManager.PNPM
            executable = "pnpm"
        elif package_manager.startswith("yarn@"):
            manager = PackageManager.YARN
            executable = "yarn"
        elif package_manager.startswith("bun@"):
            manager = PackageManager.BUN
            executable = "bun"
        elif (root / "pnpm-lock.yaml").is_file():
            manager, executable = PackageManager.PNPM, "pnpm"
        elif (root / "yarn.lock").is_file():
            manager, executable = PackageManager.YARN, "yarn"
        elif (root / "bun.lockb").is_file() or (
            root / "bun.lock"
        ).is_file():
            manager, executable = PackageManager.BUN, "bun"
        else:
            manager, executable = PackageManager.NPM, "npm"

        return PackageManagerInfo(
            manager,
            "package.json",
            executable,
        )

    def _rust(self, root: Path) -> PackageManagerInfo | None:
        if (root / "Cargo.toml").is_file():
            return PackageManagerInfo(
                PackageManager.CARGO,
                "Cargo.toml",
                "cargo",
            )
        return None

    def _go(self, root: Path) -> PackageManagerInfo | None:
        if (root / "go.mod").is_file():
            return PackageManagerInfo(
                PackageManager.GO,
                "go.mod",
                "go",
            )
        return None

    def _dotnet(self, root: Path) -> PackageManagerInfo | None:
        projects = sorted(
            (*root.glob("*.csproj"), *root.glob("*.sln"))
        )

        if projects:
            return PackageManagerInfo(
                PackageManager.DOTNET,
                projects[0].name,
                "dotnet",
            )

        return None