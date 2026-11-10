
"""Workspace sandbox and resource isolation primitives for FORGEX.

This module provides workspace path validation, bounded subprocess output
capture, process lifecycle management, and conservative environment handling.

IMPORTANT:
    This is not an operating-system security boundary. It does not provide
    filesystem namespaces, syscall filtering, network isolation, CPU quotas,
    or memory quotas. Use an OS-level sandbox, container, VM, or restricted
    account when executing untrusted code.
"""

from __future__ import annotations

import os
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Sequence


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
    """Resource limits for sandbox-managed processes and files."""

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
        workspace = Path(self.workspace).expanduser().resolve(strict=False)

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
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0 and not self.timed_out


class SandboxManager:
    """Controls filesystem access and managed subprocess execution.

    Shell execution is disabled. Callers must perform security-policy checks
    and obtain any required approval before invoking execute().
    """

    _SENSITIVE_ENV_PATTERNS = (
        re.compile(r"(?i)(TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)"),
        re.compile(r"(?i)(CREDENTIAL|AUTH|ACCESS_KEY)"),
    )

    # Only these parent-process variables are inherited by default.
    # Additional variables must be explicitly supplied to execute().
    _SAFE_INHERITED_ENV = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "SYSTEMDRIVE",
        "APPDATA",
        "LOCALAPPDATA",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
    )

    _READ_CHUNK_SIZE = 64 * 1024

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
        """Resolve and validate a path against workspace rules."""

        if not isinstance(path, (str, Path)):
            raise TypeError("Path must be a string or Path.")

        if not str(path).strip():
            raise SandboxPathError("Path cannot be empty.")

        raw_path = Path(path).expanduser()
        candidate = raw_path if raw_path.is_absolute() else self.workspace / raw_path

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
                "Direct file execution is disabled. "
                "Use approved process execution."
            )

        return resolved

    def _reject_symlink_components(self, candidate: Path) -> None:
        """Reject existing symlink components beneath the workspace."""

        try:
            relative = candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise SandboxPathError(
                "Candidate path is outside the sandbox workspace."
            ) from exc

        current = self.workspace

        for part in relative.parts:
            if part in ("", "."):
                continue

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
        """Prevent access to configured sensitive workspace files."""

        normalized = relative.as_posix().lower()

        # Git metadata must not be modified or deleted through filesystem
        # helpers. Git operations should go through the dedicated Git tools.
        if normalized == ".git" or normalized.startswith(".git/"):
            if operation in {
                FilesystemOperation.WRITE,
                FilesystemOperation.DELETE,
            }:
                raise SandboxPermissionError(
                    "Modifying Git metadata through the filesystem sandbox "
                    "is not permitted."
                )

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
        """Read a regular file within the configured size limit."""

        target = self.validate_path(path, FilesystemOperation.READ)
        max_size = self._config.limits.max_file_size_bytes

        try:
            with target.open("rb") as file:
                file_stat = os.fstat(file.fileno())

                if not stat.S_ISREG(file_stat.st_mode):
                    raise SandboxPermissionError(
                        "Only regular files can be read."
                    )

                if file_stat.st_size > max_size:
                    raise SandboxPermissionError(
                        "File exceeds the configured size limit."
                    )

                data = file.read(max_size + 1)

            if len(data) > max_size:
                raise SandboxPermissionError(
                    "File exceeds the configured size limit."
                )

            return data

        except FileNotFoundError:
            raise
        except OSError as exc:
            raise SandboxError(
                f"Unable to read file: {target}"
            ) from exc

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
            raise SandboxError(
                "File is not valid text in the requested encoding."
            ) from exc

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
            raise SandboxPermissionError(
                "Data exceeds the configured file size limit."
            )

        target = self.validate_path(path, FilesystemOperation.WRITE)

        try:
            if create_parents:
                target.parent.mkdir(parents=True, exist_ok=True)
                target = self.validate_path(path, FilesystemOperation.WRITE)

            if not target.parent.is_dir():
                raise SandboxError("Parent directory does not exist.")

            if target.exists() and target.is_dir():
                raise SandboxPermissionError(
                    "Cannot overwrite a directory."
                )

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

                # Revalidate immediately before replacement.
                target = self.validate_path(path, FilesystemOperation.WRITE)

                if target.exists() and target.is_dir():
                    raise SandboxPermissionError(
                        "Cannot overwrite a directory."
                    )

                os.replace(temporary_path, target)
                temporary_path = None

                return target

            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        pass

        except (SandboxError, TypeError, ValueError):
            raise
        except OSError as exc:
            raise SandboxError(
                f"Unable to write file: {target}"
            ) from exc

    def write_text(
        self,
        path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
        create_parents: bool = False,
    ) -> Path:
        """Write text to an authorized workspace file."""

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

        try:
            file_stat = target.lstat()

            if stat.S_ISLNK(file_stat.st_mode):
                raise SandboxPathError(
                    "Deleting symbolic links is not permitted."
                )

            if not stat.S_ISREG(file_stat.st_mode):
                raise SandboxPermissionError(
                    "Only regular files can be deleted."
                )

            target.unlink()

        except FileNotFoundError:
            raise
        except (SandboxError, TypeError, ValueError):
            raise
        except OSError as exc:
            raise SandboxError(
                f"Unable to delete file: {target}"
            ) from exc

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
        except (SandboxError, TypeError, ValueError):
            raise
        except OSError as exc:
            raise SandboxError(
                f"Unable to create directory: {target}"
            ) from exc

    def _build_environment(
        self,
        environment: dict[str, str] | None,
    ) -> dict[str, str]:
        """Build a conservative child environment."""

        parent_environment = os.environ
        result: dict[str, str] = {}

        for key in self._SAFE_INHERITED_ENV:
            value = parent_environment.get(key)
            if value is not None:
                result[key] = value

        if environment is None:
            return result

        if not isinstance(environment, dict):
            raise TypeError("Environment must be a dictionary.")

        if len(environment) > self._config.limits.max_environment_variables:
            raise SandboxPermissionError(
                "Too many environment variables."
            )

        normalized_keys: set[str] = set()

        for key, value in environment.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError(
                    "Environment keys and values must be strings."
                )

            if (
                not key
                or "=" in key
                or "\x00" in key
                or "\x00" in value
            ):
                raise ValueError("Invalid environment variable.")

            normalized_key = key.upper()

            if normalized_key in normalized_keys:
                raise ValueError(
                    f"Duplicate environment variable: {key}"
                )

            normalized_keys.add(normalized_key)

            if any(
                pattern.search(key)
                for pattern in self._SENSITIVE_ENV_PATTERNS
            ):
                raise SandboxPermissionError(
                    f"Passing sensitive environment variable is blocked: {key}"
                )

            result[key] = value

        return result

    @staticmethod
    def _capture_output(
        pipe: BinaryIO,
        limit: int,
        result: dict[str, object],
        result_key: str,
    ) -> None:
        """Drain a pipe while retaining no more than the configured limit."""

        captured = bytearray()
        truncated = False

        try:
            while True:
                chunk = pipe.read(SandboxManager._READ_CHUNK_SIZE)

                if not chunk:
                    break

                remaining = limit - len(captured)

                if remaining > 0:
                    captured.extend(chunk[:remaining])

                if len(chunk) > remaining:
                    truncated = True

        finally:
            try:
                pipe.close()
            except OSError:
                pass

        result[result_key] = bytes(captured)
        result[f"{result_key}_truncated"] = truncated

    def execute(
        self,
        command: Sequence[str],
        *,
        cwd: str | Path | None = None,
        timeout: float | None = None,
        environment: dict[str, str] | None = None,
    ) -> SandboxExecutionResult:
        """Execute an argument-based process without invoking a shell.

        The caller must perform security-policy checks and obtain approval
        before calling this method.

        Output limits apply independently to stdout and stderr. Excess output
        is drained and discarded rather than accumulated in memory.
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
            raise ValueError(
                "Command arguments must be non-empty strings without NUL."
            )

        if len(arguments) > 256:
            raise SandboxPermissionError("Too many command arguments.")

        selected_cwd = self.validate_path(
            cwd if cwd is not None else self.workspace,
            FilesystemOperation.READ,
        )

        if not selected_cwd.is_dir():
            raise SandboxPathError(
                "Execution directory must be a directory."
            )

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

        child_environment = self._build_environment(environment)

        started = time.monotonic()
        process: subprocess.Popen[bytes] | None = None

        # Keep the limit check, process creation, and registration under the
        # same lock. This prevents concurrent callers from exceeding the cap.
        with self._lock:
            if len(self._active_processes) >= self._config.limits.max_processes:
                raise SandboxPermissionError(
                    "Maximum concurrent process limit reached."
                )

            try:
                popen_options: dict[str, object] = {}

                if os.name == "nt":
                    popen_options["creationflags"] = (
                        subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                else:
                    popen_options["start_new_session"] = True

                process = subprocess.Popen(
                    arguments,
                    cwd=selected_cwd,
                    env=child_environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    close_fds=True,
                    **popen_options,
                )

                self._active_processes.add(process)

            except OSError as exc:
                raise SandboxExecutionError(
                    f"Unable to execute process: {arguments[0]}"
                ) from exc

        assert process.stdout is not None
        assert process.stderr is not None

        output_limit = self._config.limits.max_output_bytes
        stdout_result: dict[str, object] = {}
        stderr_result: dict[str, object] = {}

        stdout_thread = threading.Thread(
            target=self._capture_output,
            args=(
                process.stdout,
                output_limit,
                stdout_result,
                "stdout",
            ),
            name="forgex-stdout-reader",
            daemon=True,
        )

        stderr_thread = threading.Thread(
            target=self._capture_output,
            args=(
                process.stderr,
                output_limit,
                stderr_result,
                "stderr",
            ),
            name="forgex-stderr-reader",
            daemon=True,
        )

        timed_out = False

        try:
            stdout_thread.start()
            stderr_thread.start()

            try:
                process.wait(timeout=selected_timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate_process(process)

            # The process group is terminated on timeout so inherited pipe
            # handles held by ordinary child processes are less likely to
            # keep the reader threads blocked.
            stdout_thread.join()
            stderr_thread.join()

            duration = time.monotonic() - started

            stdout_bytes = stdout_result.get("stdout", b"")
            stderr_bytes = stderr_result.get("stderr", b"")

            if not isinstance(stdout_bytes, bytes):
                stdout_bytes = b""

            if not isinstance(stderr_bytes, bytes):
                stderr_bytes = b""

            return SandboxExecutionResult(
                command=arguments,
                return_code=(
                    process.returncode
                    if process.returncode is not None
                    else -1
                ),
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_seconds=duration,
                timed_out=timed_out,
                stdout_truncated=bool(
                    stdout_result.get("stdout_truncated", False)
                ),
                stderr_truncated=bool(
                    stderr_result.get("stderr_truncated", False)
                ),
            )

        except OSError as exc:
            self._terminate_process(process)
            raise SandboxExecutionError(
                f"Unable to execute process: {arguments[0]}"
            ) from exc

        finally:
            if process.poll() is None:
                self._terminate_process(process)

            with self._lock:
                self._active_processes.discard(process)

    @staticmethod
    def _terminate_process(
        process: subprocess.Popen[bytes],
        *,
        grace_seconds: float = 2.0,
    ) -> None:
        """Terminate a process tree where platform support permits."""

        if process.poll() is not None:
            return

        if os.name == "nt":
            # First try a graceful console process-group interrupt.
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                process.wait(timeout=grace_seconds)
                return
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass

            # taskkill /T targets descendants on Windows.
            try:
                subprocess.run(
                    [
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=grace_seconds + 2.0,
                    shell=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass

            if process.poll() is None:
                process.kill()

            process.wait()
            return

        # start_new_session=True makes the child the leader of its own
        # process group. Signal the group rather than just the parent.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            if process.poll() is None:
                process.terminate()

        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                if process.poll() is None:
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
