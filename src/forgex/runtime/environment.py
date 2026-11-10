
"""Runtime environment detection for FORGEX."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class RuntimeEnvironment:
    """Describes the host environment in which FORGEX is running."""

    operating_system: str
    architecture: str
    platform_release: str
    python_version: str
    python_executable: Path
    working_directory: Path
    shell_name: str
    shell_executable: Path | None
    path_separator: str
    is_wsl: bool
    is_container: bool
    supports_ansi: bool

    @classmethod
    def detect(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> RuntimeEnvironment:
        """Detect the current host runtime environment."""

        environment = os.environ if environ is None else environ

        system = platform.system().lower()

        if system == "windows":
            operating_system = "windows"
        elif system == "linux":
            operating_system = "linux"
        elif system == "darwin":
            operating_system = "macos"
        else:
            operating_system = system or "unknown"

        shell_name, shell_executable = cls._detect_shell(
            operating_system,
            environment,
        )

        return cls(
            operating_system=operating_system,
            architecture=platform.machine().lower(),
            platform_release=platform.release(),
            python_version=platform.python_version(),
            python_executable=Path(sys.executable).resolve(strict=False),
            working_directory=(
                cwd.expanduser().resolve(strict=False)
                if cwd is not None
                else Path.cwd().resolve(strict=False)
            ),
            shell_name=shell_name,
            shell_executable=shell_executable,
            path_separator=os.pathsep,
            is_wsl=cls._is_wsl(operating_system, environment),
            is_container=cls._is_container(operating_system, environment),
            supports_ansi=cls._supports_ansi(operating_system, environment),
        )

    @staticmethod
    def _detect_shell(
        operating_system: str,
        environ: Mapping[str, str],
    ) -> tuple[str, Path | None]:
        """Detect the preferred interactive shell."""

        if operating_system == "windows":
            candidates = [
                ("powershell", environ.get("POWERSHELL_EXE")),
                ("pwsh", shutil.which("pwsh")),
                ("powershell", shutil.which("powershell")),
                ("cmd", environ.get("COMSPEC")),
            ]
        else:
            shell = environ.get("SHELL")
            candidates = [
                (
                    Path(shell).name if shell else "",
                    shell,
                ),
                ("bash", shutil.which("bash")),
                ("zsh", shutil.which("zsh")),
                ("sh", shutil.which("sh")),
            ]

        for name, executable in candidates:
            if not executable:
                continue

            path = Path(executable).expanduser()

            if path.is_file():
                return name or path.name, path.resolve(strict=False)

            discovered = shutil.which(executable)

            if discovered:
                return name or Path(discovered).name, Path(
                    discovered
                ).resolve(strict=False)

        return "unknown", None

    @staticmethod
    def _is_wsl(
        operating_system: str,
        environ: Mapping[str, str],
    ) -> bool:
        """Determine whether the current process runs inside WSL."""

        if operating_system != "linux":
            return False

        if "WSL_DISTRO_NAME" in environ or "WSL_INTEROP" in environ:
            return True

        try:
            release = platform.uname().release.lower()
        except OSError:
            return False

        return "microsoft" in release or "wsl" in release

    @staticmethod
    def _is_container(
        operating_system: str,
        environ: Mapping[str, str],
    ) -> bool:
        """Detect common Linux container environments."""

        if operating_system != "linux":
            return False

        if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
            return True

        try:
            cgroup = Path("/proc/1/cgroup").read_text(
                encoding="utf-8",
                errors="replace",
            ).lower()
        except OSError:
            return False

        markers = ("docker", "containerd", "kubepods", "podman")
        return any(marker in cgroup for marker in markers)

    @staticmethod
    def _supports_ansi(
        operating_system: str,
        environ: Mapping[str, str],
    ) -> bool:
        """Determine whether the current terminal likely supports ANSI."""

        if environ.get("NO_COLOR") is not None:
            return False

        if environ.get("TERM", "").lower() == "dumb":
            return False

        if operating_system != "windows":
            return bool(environ.get("TERM"))

        return (
            bool(environ.get("WT_SESSION"))
            or bool(environ.get("ANSICON"))
            or environ.get("TERM_PROGRAM", "").lower() == "vscode"
        )

    @property
    def is_windows(self) -> bool:
        return self.operating_system == "windows"

    @property
    def is_linux(self) -> bool:
        return self.operating_system == "linux"

    @property
    def is_macos(self) -> bool:
        return self.operating_system == "macos"

    @property
    def is_posix(self) -> bool:
        return self.operating_system in {"linux", "macos"}

    def to_dict(self) -> dict[str, object]:
        """Return a serialization-friendly environment snapshot."""

        return {
            "operating_system": self.operating_system,
            "architecture": self.architecture,
            "platform_release": self.platform_release,
            "python_version": self.python_version,
            "python_executable": str(self.python_executable),
            "working_directory": str(self.working_directory),
            "shell_name": self.shell_name,
            "shell_executable": (
                str(self.shell_executable)
                if self.shell_executable is not None
                else None
            ),
            "path_separator": self.path_separator,
            "is_wsl": self.is_wsl,
            "is_container": self.is_container,
            "supports_ansi": self.supports_ansi,
        }
