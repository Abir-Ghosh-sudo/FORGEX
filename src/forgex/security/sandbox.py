
"""Workspace sandbox and resource isolation primitives for FORGEX."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Sequence


class SandboxError(Exception):
    """Base exception for sandbox violations."""


class SandboxPathError(SandboxError):
    """Raised when a path escapes the authorized workspace."""


class SandboxPermissionError(SandboxError):
    """Raised when a protected filesystem operation is attempted."""


class SandboxExecutionError(SandboxError):
    """Raised when process execution fails."""


class FilesystemOperation(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    """Resource limits for sandbox-managed processes."""

    timeout_seconds: float = 120.0
    max_output_bytes: int = 2_000_000
    max_file_size_bytes: int = 50_000_000
    max_processes: int = 4
    max_environment_variables: int = 64

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive.")

        if self.max_output_bytes <= 0:
            raise ValueError("Maximum output size must be positive.")

        if self.max_file_size_bytes <= 0:
            raise ValueError("Maximum file size must be positive.")

        if self.max_processes < 1:
            raise ValueError("At least one process must be allowed.")

        if self.max_environment_variables < 0:
            raise ValueError("Environment variable limit cannot be negative.")


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """Configuration for a workspace sandbox."""

    workspace: Path
    read_only: bool = False
    allow_symlinks: bool = False
    allow_hidden_files: bool = True
    protected_paths: tuple[str, ...] = (
        ".git/config",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa",
        "id_ed25519",
    )
    limits: SandboxLimits = SandboxLimits()

    def __post_init__(self) -> None:
        workspace = self.workspace.expanduser().resolve(strict=False)

        object.__setattr__(self, "workspace", workspace)

        if not workspace.exists():
            raise ValueError(f"Workspace does not exist: {workspace}")

        if not workspace.is_dir():
            raise ValueError("Sandbox workspace must be a directory.")


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    """Result returned after a sandbox-managed process finishes."""

    command: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0 and not self.timed_out


class SandboxManager:
    """Controls filesystem access and process execution within a workspace.

    IMPORTANT:
        This class provides workspace path validation and subprocess
        management, not an operating-system security boundary.

        For untrusted code, use an OS-level sandbox, container, VM,
        restricted account, or equivalent isolation mechanism.
    """

    _SENSITIVE_ENV_PATTERNS = (
        re.compile(r"(?i)(TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)"),
        re.compile(r"(?i)(CREDENTIAL|AUTH|ACCESS_KEY)"),
    )

    def __init__(self, config: SandboxConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._active_processes: set[subprocess.Popen[bytes]] = set()

    @property
    def workspace(self) -> Path:
        return self._config.workspace

    @property
    def config(self) -> SandboxConfig:
        return self._config

    def validate_path(
        self,
        path: str | Path,
        operation: FilesystemOperation = FilesystemOperation.READ,
    ) -> Path:
        """Resolve and validate a filesystem path against sandbox rules."""

        raw_path = Path(path).expanduser()

        if not str(path).strip():
            raise SandboxPathError("Path cannot be empty.")

        if raw_path.is_absolute():
            candidate = raw_path
        else:
            candidate = self.workspace / raw_path

        resolved = candidate.resolve(strict=False)

        try:
            relative = resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise SandboxPathError(
                f"Path escapes sandbox workspace: {path}"
            ) from exc

        if not self._config.allow_hidden_files:
            if any(part.startswith(".") for part in relative.parts):
                raise SandboxPermissionError(
                    f"Hidden file access is disabled: {relative}"
                )

        if not self._config.allow_symlinks:
            self._reject_symlink_components(candidate)

        self._check_protected_path(relative, operation)

        if operation in {
            FilesystemOperation.WRITE,
            FilesystemOperation.DELETE,
        } and self._config.read_only:
            raise SandboxPermissionError(
                "Sandbox is configured as read-only."
            )

        if operation == FilesystemOperation.EXECUTE:
            raise SandboxPermissionError(
                "Direct file execution is disabled. Use approved process execution."
            )

        return resolved

    def _reject_symlink_components(self, candidate: Path) -> None:
        """Reject existing symlink components, including workspace escapes."""

        try:
            relative = candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise SandboxPathError(
                "Candidate path is outside the sandbox workspace."
            ) from exc

        current = self.workspace

        for part in relative.parts:
            current = current / part

            try:
                if current.is_symlink():
                    raise SandboxPathError(
                        f"Symbolic links are disabled: {current}"
                    )
            except OSError as exc:
                raise SandboxPathError(
                    f"Unable to inspect path component: {current}"
                ) from exc

    def _check_protected_path(
        self,
        relative: Path,
        operation: FilesystemOperation,
    ) -> None:
        """Prevent access to sensitive workspace files."""

        normalized = relative.as_posix().lower()

        for pattern in self._config.protected_paths:
            if Path(normalized).match(pattern.lower()):
                raise SandboxPermissionError(
                    f"Protected path access denied: {relative}"
                )

        if operation == FilesystemOperation.DELETE:
            if normalized == ".git" or normalized.startswith(".git/"):
                raise SandboxPermissionError(
                    "Deleting Git metadata is not permitted."
                )

    def read_bytes(self, path: str | Path) -> bytes:
        """Read a file after validating its path and size."""

        target = self.validate_path(path, FilesystemOperation.READ)

        try:
            file_stat = target.stat()

            if not stat.S_ISREG(file_stat.st_mode):
                raise SandboxPermissionError("Only regular files can be read.")

            if file_stat.st_size > self._config.limits.max_file_size_bytes:
                raise SandboxPermissionError("File exceeds the configured size limit.")

            with target.open("rb") as file:
                data = file.read(self._config.limits.max_file_size_bytes + 1)

            if len(data) > self._config.limits.max_file_size_bytes:
                raise SandboxPermissionError("File exceeds the configured size limit.")

            return data

        except FileNotFoundError:
            raise
        except OSError as exc:
            raise SandboxError(f"Unable to read file: {target}") from exc

    def read_text(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
    ) -> str:
        """Read a text file using the requested encoding."""

        try:
            return self.read_bytes(path).decode(encoding)
        except UnicodeDecodeError as exc:
            raise SandboxError("File is not valid text in the requested encoding.") from exc

    def write_bytes(
        self,
        path: str | Path,
        data: bytes,
        *,
        create_parents: bool = False,
    ) -> Path:
        """Write bytes atomically to an authorized workspace file."""

        if not isinstance(data, bytes):
            raise TypeError("Data must be bytes.")

        if len(data) > self._config.limits.max_file_size_bytes:
            raise SandboxPermissionError("Data exceeds the configured file size limit.")

        target = self.validate_path(path, FilesystemOperation.WRITE)

        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)

            # Revalidate after creating parent directories.
            target = self.validate_path(path, FilesystemOperation.WRITE)

        if not target.parent.is_dir():
            raise SandboxError("Parent directory does not exist.")

        if target.exists() and target.is_dir():
            raise SandboxPermissionError("Cannot overwrite a directory.")

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=".forgex-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(data)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            # Check again before replacement.
            self.validate_path(path, FilesystemOperation.WRITE)

            os.replace(temporary_path, target)
            temporary_path = None

            return target

        except OSError as exc:
            raise SandboxError(f"Unable to write file: {target}") from exc

        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def write_text(
        self,
        path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
        create_parents: bool = False,
    ) -> Path:
        """Write text to a workspace file."""

        if not isinstance(content, str):
            raise TypeError("Content must be a string.")

        return self.write_bytes(
            path,
            content.encode(encoding),
            create_parents=create_parents,
        )

    def delete_file(self, path: str | Path) -> None:
        """Delete a regular file inside the workspace."""

        target = self.validate_path(path, FilesystemOperation.DELETE)

        if target.is_symlink():
            raise SandboxPathError("Deleting symbolic links is not permitted.")

        if not target.is_file():
            raise SandboxPermissionError("Only regular files can be deleted.")

        try:
            target.unlink()
        except OSError as exc:
            raise SandboxError(f"Unable to delete file: {target}") from exc

    def create_directory(
        self,
        path: str | Path,
        *,
        parents: bool = True,
        exist_ok: bool = True,
    ) -> Path:
        """Create an authorized workspace directory."""

        target = self.validate_path(path, FilesystemOperation.WRITE)

        try:
            target.mkdir(parents=parents, exist_ok=exist_ok)
            return self.validate_path(path, FilesystemOperation.WRITE)
        except OSError as exc:
            raise SandboxError(f"Unable to create directory: {target}") from exc

    def execute(
        self,
        command: Sequence[str],
        *,
        cwd: str | Path | None = None,
        timeout: float | None = None,
        environment: dict[str, str] | None = None,
    ) -> SandboxExecutionResult:
        """Execute an argument-based process in the authorized workspace.

        Shell execution is deliberately disabled.

        The caller must perform security-policy checks and obtain approval
        before calling this method.
        """

        if isinstance(command, (str, bytes)) or not command:
            raise ValueError(
                "Command must be a non-empty sequence of executable arguments."
            )

        arguments = tuple(command)

        if any(
            not isinstance(argument, str)
            or not argument
            or "\x00" in argument
            for argument in arguments
        ):
            raise ValueError("Command arguments must be non-empty strings without NUL.")

        if len(arguments) > 256:
            raise SandboxPermissionError("Too many command arguments.")

        selected_cwd = self.validate_path(
            cwd or self.workspace,
            FilesystemOperation.READ,
        )

        if not selected_cwd.is_dir():
            raise SandboxPathError("Execution directory must be a directory.")

        selected_timeout = (
            timeout
            if timeout is not None
            else self._config.limits.timeout_seconds
        )

        if selected_timeout <= 0:
            raise ValueError("Execution timeout must be positive.")

        if selected_timeout > self._config.limits.timeout_seconds:
            raise SandboxPermissionError(
                "Requested timeout exceeds sandbox limits."
            )

        if environment is not None:
            if len(environment) > self._config.limits.max_environment_variables:
                raise SandboxPermissionError(
                    "Too many environment variables."
                )

            for key, value in environment.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise TypeError("Environment keys and values must be strings.")

                if not key or "=" in key or "\x00" in key or "\x00" in value:
                    raise ValueError("Invalid environment variable.")

                if any(
                    pattern.search(key)
                    for pattern in self._SENSITIVE_ENV_PATTERNS
                ):
                    raise SandboxPermissionError(
                        f"Passing sensitive environment variable is blocked: {key}"
                    )

        env = os.environ.copy()

        if environment is not None:
            env.update(environment)

        with self._lock:
            if len(self._active_processes) >= self._config.limits.max_processes:
                raise SandboxPermissionError(
                    "Maximum concurrent process limit reached."
                )

        import time

        started = time.monotonic()
        process: subprocess.Popen[bytes] | None = None

        try:
            process = subprocess.Popen(
                arguments,
                cwd=selected_cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )

            with self._lock:
                self._active_processes.add(process)

            try:
                stdout_bytes, stderr_bytes = process.communicate(
                    timeout=selected_timeout
                )
                timed_out = False

            except subprocess.TimeoutExpired:
                self._terminate_process(process)

                stdout_bytes, stderr_bytes = process.communicate()
                timed_out = True

            duration = time.monotonic() - started
            output_limit = self._config.limits.max_output_bytes

            stdout_bytes = stdout_bytes[:output_limit]
            stderr_bytes = stderr_bytes[:output_limit]

            return SandboxExecutionResult(
                command=arguments,
                return_code=process.returncode if process.returncode is not None else -1,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_seconds=duration,
                timed_out=timed_out,
            )

        except OSError as exc:
            raise SandboxExecutionError(
                f"Unable to execute process: {arguments[0]}"
            ) from exc

        finally:
            if process is not None:
                with self._lock:
                    self._active_processes.discard(process)

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes]) -> None:
        """Terminate a process and escalate to kill if necessary."""

        if process.poll() is not None:
            return

        process.terminate()

        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def terminate_all(self) -> int:
        """Terminate all currently registered processes."""

        with self._lock:
            processes = list(self._active_processes)

        terminated = 0

        for process in processes:
            if process.poll() is None:
                self._terminate_process(process)
                terminated += 1

        return terminated

    def cleanup(self) -> None:
        """Terminate managed processes and release internal resources."""

        self.terminate_all()

    def __enter__(self) -> SandboxManager:
        return self

    def __exit__(self, *args: object) -> None:
        self.cleanup()
