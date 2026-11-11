"""Test framework detection and command resolution."""

from __future__ import annotations

import json
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.testing.models import TestFramework, TestRequest


class FrameworkDetectionError(RuntimeError):
    """Raised when framework detection fails."""


@dataclass(frozen=True, slots=True)
class FrameworkInfo:
    framework: TestFramework
    command: tuple[str, ...]
    project_file: str | None = None
    confidence: float = 1.0


class FrameworkDetector:
    """Detect test frameworks from project files."""

    def detect(self, workspace: Path) -> FrameworkInfo:
        root = Path(workspace).expanduser().resolve()

        if not root.is_dir():
            raise FrameworkDetectionError(
                f"Workspace does not exist: {root}"
            )

        checks = (
            self._python,
            self._node,
            self._rust,
            self._go,
            self._dotnet,
        )

        for check in checks:
            result = check(root)
            if result is not None:
                return result

        raise FrameworkDetectionError(
            f"No supported test framework detected in {root}"
        )

    def _python(self, root: Path) -> FrameworkInfo | None:
        pyproject = root / "pyproject.toml"

        if pyproject.is_file():
            try:
                with pyproject.open("rb") as file:
                    data = tomllib.load(file)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise FrameworkDetectionError(
                    f"Invalid pyproject.toml: {exc}"
                ) from exc

            if (
                "pytest" in data.get("tool", {})
                or "pytest" in data.get("project", {}).get(
                    "optional-dependencies", {}
                )
            ):
                return FrameworkInfo(
                    TestFramework.PYTEST,
                    ("pytest",),
                    "pyproject.toml",
                )

        if (root / "pytest.ini").is_file() or (
            root / "conftest.py"
        ).is_file():
            return FrameworkInfo(
                TestFramework.PYTEST,
                ("pytest",),
            )

        if (root / "tests").is_dir() and any(
            root.glob("test_*.py")
        ):
            return FrameworkInfo(
                TestFramework.PYTEST,
                ("pytest",),
            )

        if any(root.glob("test_*.py")):
            return FrameworkInfo(
                TestFramework.PYTEST,
                ("pytest",),
            )

        if (root / "unittest.cfg").is_file():
            return FrameworkInfo(
                TestFramework.UNITTEST,
                ("python", "-m", "unittest", "discover"),
                "unittest.cfg",
            )

        return None

    def _node(self, root: Path) -> FrameworkInfo | None:
        package_json = root / "package.json"

        if not package_json.is_file():
            return None

        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FrameworkDetectionError(
                f"Invalid package.json: {exc}"
            ) from exc

        dependencies = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }

        scripts = data.get("scripts", {})
        test_script = scripts.get("test")

        if "vitest" in dependencies:
            return FrameworkInfo(
                TestFramework.VITEST,
                ("npx", "--no-install", "vitest", "run"),
                "package.json",
            )

        if "jest" in dependencies:
            return FrameworkInfo(
                TestFramework.JEST,
                ("npx", "--no-install", "jest", "--runInBand"),
                "package.json",
            )

        if test_script:
            return FrameworkInfo(
                TestFramework.NODE,
                ("npm", "test", "--"),
                "package.json",
                confidence=0.8,
            )

        return None

    def _rust(self, root: Path) -> FrameworkInfo | None:
        cargo_file = root / "Cargo.toml"

        if cargo_file.is_file():
            return FrameworkInfo(
                TestFramework.CARGO,
                ("cargo", "test"),
                "Cargo.toml",
            )

        return None

    def _go(self, root: Path) -> FrameworkInfo | None:
        go_file = root / "go.mod"

        if go_file.is_file():
            return FrameworkInfo(
                TestFramework.GO,
                ("go", "test", "./..."),
                "go.mod",
            )

        return None

    def _dotnet(self, root: Path) -> FrameworkInfo | None:
        project_files = sorted(
            (*root.glob("*.sln"), *root.glob("*.csproj"))
        )

        if project_files:
            return FrameworkInfo(
                TestFramework.DOTNET,
                ("dotnet", "test", str(project_files[0])),
                project_files[0].name,
            )

        return None


class TestCommandResolver:
    """Build safe test commands from a request."""

    def __init__(self, detector: FrameworkDetector | None = None):
        self.detector = detector or FrameworkDetector()

    def resolve(self, request: TestRequest) -> tuple[str, ...]:
        if request.framework == TestFramework.AUTO:
            info = self.detector.detect(request.workspace)
            framework = info.framework
            command = info.command
        else:
            framework = request.framework
            command = self._default_command(framework, request.workspace)

        if not command:
            raise FrameworkDetectionError(
                f"Unsupported test framework: {framework}"
            )

        args = list(command)

        if framework == TestFramework.PYTEST:
            if request.coverage:
                args.extend(("--cov", "--cov-report=term-missing"))
            if request.fail_fast:
                args.append("-x")
            for marker in request.markers:
                args.extend(("-m", marker))

        elif framework in (TestFramework.JEST, TestFramework.VITEST):
            if request.fail_fast:
                args.append("--bail")

        elif framework == TestFramework.GO and request.fail_fast:
            args.append("-failfast")

        args.extend(request.test_paths)
        args.extend(request.extra_args)

        return tuple(args)

    @staticmethod
    def _default_command(
        framework: TestFramework,
        workspace: Path,
    ) -> tuple[str, ...]:
        commands = {
            TestFramework.PYTEST: ("pytest",),
            TestFramework.UNITTEST: (
                "python", "-m", "unittest", "discover"
            ),
            TestFramework.NODE: ("npm", "test", "--"),
            TestFramework.JEST: (
                "npx", "--no-install", "jest", "--runInBand"
            ),
            TestFramework.VITEST: (
                "npx", "--no-install", "vitest", "run"
            ),
            TestFramework.CARGO: ("cargo", "test"),
            TestFramework.GO: ("go", "test", "./..."),
            TestFramework.DOTNET: (
                "dotnet", "test", str(workspace)
            ),
        }

        return commands.get(framework, ())

    @staticmethod
    def is_available(command: tuple[str, ...]) -> bool:
        if not command:
            return False

        executable = command[0]

        if Path(executable).is_absolute():
            return Path(executable).is_file()

        return shutil.which(executable) is not None