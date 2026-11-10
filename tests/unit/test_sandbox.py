
"""Unit tests for FORGEX workspace sandbox."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from forgex.security.sandbox import (
    FilesystemOperation,
    SandboxConfig,
    SandboxExecutionError,
    SandboxLimits,
    SandboxManager,
    SandboxPathError,
    SandboxPermissionError,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def sandbox(workspace: Path) -> SandboxManager:
    return SandboxManager(SandboxConfig(workspace=workspace))


@pytest.fixture
def restricted_sandbox(workspace: Path) -> SandboxManager:
    return SandboxManager(
        SandboxConfig(
            workspace=workspace,
            limits=SandboxLimits(
                timeout_seconds=5,
                max_output_bytes=128,
                max_file_size_bytes=1024,
                max_processes=2,
                max_environment_variables=4,
            ),
        )
    )


class TestSandboxConfiguration:
    def test_workspace_is_resolved(self, workspace: Path) -> None:
        manager = SandboxManager(SandboxConfig(workspace=workspace))
        assert manager.workspace == workspace.resolve()

    def test_nonexistent_workspace_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            SandboxConfig(workspace=tmp_path / "missing")

    def test_file_as_workspace_rejected(self, tmp_path: Path) -> None:
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")

        with pytest.raises(ValueError):
            SandboxConfig(workspace=file_path)

    def test_invalid_limits_rejected(self) -> None:
        with pytest.raises(ValueError):
            SandboxLimits(timeout_seconds=0)

        with pytest.raises(ValueError):
            SandboxLimits(max_output_bytes=0)

        with pytest.raises(ValueError):
            SandboxLimits(max_processes=0)

    def test_negative_environment_limit_rejected(self) -> None:
        with pytest.raises(ValueError):
            SandboxLimits(max_environment_variables=-1)


class TestPathValidation:
    def test_relative_path(self, sandbox: SandboxManager) -> None:
        target = sandbox.validate_path("src/main.py")
        assert target == sandbox.workspace / "src" / "main.py"

    def test_absolute_path_inside_workspace(
        self,
        sandbox: SandboxManager,
    ) -> None:
        target = sandbox.workspace / "file.txt"
        assert sandbox.validate_path(target) == target

    def test_path_traversal_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(SandboxPathError):
            sandbox.validate_path("../outside.txt")

    def test_absolute_path_outside_rejected(
        self,
        sandbox: SandboxManager,
        tmp_path: Path,
    ) -> None:
        outside = tmp_path.parent / "outside.txt"

        with pytest.raises(SandboxPathError):
            sandbox.validate_path(outside)

    def test_empty_path_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(SandboxPathError):
            sandbox.validate_path("")

    def test_hidden_files_allowed_by_default(
        self,
        sandbox: SandboxManager,
    ) -> None:
        assert sandbox.validate_path(".hidden").name == ".hidden"

    def test_hidden_files_can_be_disabled(
        self,
        workspace: Path,
    ) -> None:
        manager = SandboxManager(
            SandboxConfig(
                workspace=workspace,
                allow_hidden_files=False,
            )
        )

        with pytest.raises(SandboxPermissionError):
            manager.validate_path(".secret")

    def test_symlink_rejected_when_disabled(
        self,
        sandbox: SandboxManager,
        tmp_path: Path,
    ) -> None:
        outside = tmp_path.parent / "external-target"
        outside.mkdir(exist_ok=True)

        link = sandbox.workspace / "external-link"

        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation is unavailable.")

        with pytest.raises(SandboxPathError):
            sandbox.validate_path("external-link/file.txt")

    def test_execute_filesystem_operation_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(SandboxPermissionError):
            sandbox.validate_path("program.py", FilesystemOperation.EXECUTE)


class TestProtectedPaths:
    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.production",
            "private.pem",
            "private.key",
            "id_rsa",
            "id_ed25519",
        ],
    )
    def test_sensitive_files_protected(
        self,
        sandbox: SandboxManager,
        path: str,
    ) -> None:
        with pytest.raises(SandboxPermissionError):
            sandbox.validate_path(path)

    def test_git_metadata_write_protected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(SandboxPermissionError):
            sandbox.validate_path(
                ".git/config",
                FilesystemOperation.WRITE,
            )

    def test_git_metadata_delete_protected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(SandboxPermissionError):
            sandbox.validate_path(
                ".git/HEAD",
                FilesystemOperation.DELETE,
            )

    def test_git_metadata_read_allowed(
        self,
        sandbox: SandboxManager,
    ) -> None:
        assert sandbox.validate_path(".git/HEAD").name == "HEAD"


class TestFilesystemOperations:
    def test_read_bytes(self, sandbox: SandboxManager) -> None:
        target = sandbox.workspace / "hello.txt"
        target.write_bytes(b"hello")

        assert sandbox.read_bytes("hello.txt") == b"hello"

    def test_read_text(self, sandbox: SandboxManager) -> None:
        target = sandbox.workspace / "hello.txt"
        target.write_text("Hello FORGEX", encoding="utf-8")

        assert sandbox.read_text("hello.txt") == "Hello FORGEX"

    def test_read_missing_file(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(FileNotFoundError):
            sandbox.read_bytes("missing.txt")

    def test_read_file_size_limit(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        target = restricted_sandbox.workspace / "large.txt"
        target.write_bytes(b"x" * 2048)

        with pytest.raises(SandboxPermissionError):
            restricted_sandbox.read_bytes("large.txt")

    def test_write_bytes(self, sandbox: SandboxManager) -> None:
        target = sandbox.write_bytes("output.bin", b"FORGEX")

        assert target.read_bytes() == b"FORGEX"

    def test_write_text(self, sandbox: SandboxManager) -> None:
        target = sandbox.write_text("output.txt", "Hello")

        assert target.read_text() == "Hello"

    def test_write_creates_parent_directories(
        self,
        sandbox: SandboxManager,
    ) -> None:
        target = sandbox.write_text(
            "nested/deep/file.txt",
            "content",
            create_parents=True,
        )

        assert target.read_text() == "content"

    def test_write_size_limit(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(SandboxPermissionError):
            restricted_sandbox.write_bytes("large.bin", b"x" * 2048)

    def test_write_rejects_non_bytes(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(TypeError):
            sandbox.write_bytes("file.txt", "not bytes")  # type: ignore[arg-type]

    def test_read_only_sandbox_blocks_writes(
        self,
        workspace: Path,
    ) -> None:
        manager = SandboxManager(
            SandboxConfig(workspace=workspace, read_only=True)
        )

        with pytest.raises(SandboxPermissionError):
            manager.write_text("file.txt", "content")

    def test_read_only_sandbox_blocks_delete(
        self,
        workspace: Path,
    ) -> None:
        target = workspace / "file.txt"
        target.write_text("content")

        manager = SandboxManager(
            SandboxConfig(workspace=workspace, read_only=True)
        )

        with pytest.raises(SandboxPermissionError):
            manager.delete_file("file.txt")

    def test_delete_regular_file(self, sandbox: SandboxManager) -> None:
        target = sandbox.workspace / "delete.txt"
        target.write_text("delete")

        sandbox.delete_file("delete.txt")

        assert not target.exists()

    def test_delete_directory_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        (sandbox.workspace / "directory").mkdir()

        with pytest.raises(SandboxPermissionError):
            sandbox.delete_file("directory")

    def test_create_directory(self, sandbox: SandboxManager) -> None:
        target = sandbox.create_directory("a/b/c")

        assert target.is_dir()


class TestEnvironmentHandling:
    def test_safe_environment_variable_allowed(
        self,
        sandbox: SandboxManager,
    ) -> None:
        env = sandbox._build_environment({"FORGEX_TEST": "enabled"})
        assert env["FORGEX_TEST"] == "enabled"

    @pytest.mark.parametrize(
        "key",
        [
            "API_KEY",
            "ACCESS_TOKEN",
            "DATABASE_PASSWORD",
            "PRIVATE_KEY",
            "MY_SECRET",
        ],
    )
    def test_sensitive_environment_variable_blocked(
        self,
        sandbox: SandboxManager,
        key: str,
    ) -> None:
        with pytest.raises(SandboxPermissionError):
            sandbox._build_environment({key: "secret-value"})

    def test_environment_variable_count_limit(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        env = {
            f"FORGEX_{index}": str(index)
            for index in range(5)
        }

        with pytest.raises(SandboxPermissionError):
            restricted_sandbox._build_environment(env)

    def test_invalid_environment_type(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(TypeError):
            sandbox._build_environment(  # type: ignore[arg-type]
                {"INVALID": 123}
            )

    def test_environment_values_with_nul_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(ValueError):
            sandbox._build_environment({"VALUE": "bad\x00value"})

    def test_parent_secrets_not_inherited(
        self,
        sandbox: SandboxManager,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FORGEX_TEST_SECRET", "parent-secret")

        env = sandbox._build_environment(None)

        assert "FORGEX_TEST_SECRET" not in env


class TestProcessExecution:
    @staticmethod
    def python_command(code: str) -> list[str]:
        return [sys.executable, "-c", code]

    def test_execute_success(self, sandbox: SandboxManager) -> None:
        result = sandbox.execute(
            self.python_command("print('hello')")
        )

        assert result.succeeded
        assert result.stdout.strip() == "hello"
        assert result.return_code == 0

    def test_execute_failure(self, sandbox: SandboxManager) -> None:
        result = sandbox.execute(
            self.python_command("raise SystemExit(7)")
        )

        assert not result.succeeded
        assert result.return_code == 7

    def test_shell_execution_not_enabled(
        self,
        sandbox: SandboxManager,
    ) -> None:
        result = sandbox.execute(
            self.python_command("print('safe')")
        )

        assert result.succeeded

    def test_string_command_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(ValueError):
            sandbox.execute("python -c pass")  # type: ignore[arg-type]

    def test_empty_command_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(ValueError):
            sandbox.execute([])

    def test_invalid_argument_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(ValueError):
            sandbox.execute(["python", "\x00"])

    def test_too_many_arguments_rejected(
        self,
        sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(SandboxPermissionError):
            sandbox.execute(["python"] + ["x"] * 256)

    def test_custom_working_directory(
        self,
        sandbox: SandboxManager,
    ) -> None:
        directory = sandbox.workspace / "subdir"
        directory.mkdir()

        result = sandbox.execute(
            self.python_command("import os; print(os.getcwd())"),
            cwd=directory,
        )

        assert result.succeeded
        assert str(directory) in result.stdout

    def test_working_directory_outside_rejected(
        self,
        sandbox: SandboxManager,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(SandboxPathError):
            sandbox.execute(
                self.python_command("print('bad')"),
                cwd=tmp_path.parent,
            )

    def test_custom_environment(
        self,
        sandbox: SandboxManager,
    ) -> None:
        result = sandbox.execute(
            self.python_command(
                "import os; print(os.environ['FORGEX_TEST_VALUE'])"
            ),
            environment={"FORGEX_TEST_VALUE": "works"},
        )

        assert result.succeeded
        assert "works" in result.stdout

    def test_output_truncation(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        result = restricted_sandbox.execute(
            self.python_command("print('x' * 1000)")
        )

        assert result.succeeded
        assert len(result.stdout.encode("utf-8")) <= 128
        assert result.stdout_truncated

    def test_stderr_truncation(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        result = restricted_sandbox.execute(
            self.python_command(
                "import sys; sys.stderr.write('x' * 1000)"
            )
        )

        assert result.succeeded
        assert len(result.stderr.encode("utf-8")) <= 128
        assert result.stderr_truncated

    def test_output_streams_are_drained_concurrently(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        result = restricted_sandbox.execute(
            self.python_command(
                "import sys; "
                "sys.stdout.write('o' * 100000); "
                "sys.stderr.write('e' * 100000)"
            )
        )

        assert result.return_code == 0
        assert result.stdout_truncated
        assert result.stderr_truncated

    def test_timeout(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        result = restricted_sandbox.execute(
            self.python_command("import time; time.sleep(10)"),
            timeout=0.2,
        )

        assert result.timed_out
        assert not result.succeeded

    def test_timeout_cannot_exceed_configured_limit(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        with pytest.raises(SandboxPermissionError):
            restricted_sandbox.execute(
                self.python_command("print('x')"),
                timeout=10,
            )

    def test_process_slots_released_after_execution(
        self,
        restricted_sandbox: SandboxManager,
    ) -> None:
        for _ in range(4):
            result = restricted_sandbox.execute(
                self.python_command("print('ok')")
            )
            assert result.succeeded

        assert len(restricted_sandbox._active_processes) == 0

    def test_process_limit_is_enforced(
        self,
        workspace: Path,
    ) -> None:
        manager = SandboxManager(
            SandboxConfig(
                workspace=workspace,
                limits=SandboxLimits(
                    timeout_seconds=5,
                    max_processes=1,
                ),
            )
        )

        entered = threading.Event()
        release = threading.Event()
        errors: list[Exception] = []

        def run_process() -> None:
            try:
                manager.execute(
                    self.python_command(
                        "import time; time.sleep(1.5)"
                    )
                )
            except Exception as exc:
                errors.append(exc)
            finally:
                entered.set()

        thread = threading.Thread(target=run_process)
        thread.start()

        deadline = time.monotonic() + 3

        while time.monotonic() < deadline:
            with manager._lock:
                active = len(manager._active_processes)

            if active:
                break

            time.sleep(0.01)

        with pytest.raises(SandboxPermissionError):
            manager.execute(
                self.python_command("print('second')")
            )

        thread.join(timeout=5)

        assert not thread.is_alive()
        assert not errors

    def test_terminate_all(
        self,
        workspace: Path,
    ) -> None:
        manager = SandboxManager(
            SandboxConfig(
                workspace=workspace,
                limits=SandboxLimits(timeout_seconds=10),
            )
        )

        started = threading.Event()

        def run_process() -> None:
            started.set()
            try:
                manager.execute(
                    self.python_command(
                        "import time; time.sleep(8)"
                    )
                )
            except SandboxExecutionError:
                pass

        thread = threading.Thread(target=run_process)
        thread.start()
        started.wait(timeout=2)

        deadline = time.monotonic() + 3

        while time.monotonic() < deadline:
            with manager._lock:
                if manager._active_processes:
                    break
            time.sleep(0.01)

        terminated = manager.terminate_all()
        thread.join(timeout=5)

        assert terminated >= 0
        assert not thread.is_alive()

    def test_duration_is_non_negative(
        self,
        sandbox: SandboxManager,
    ) -> None:
        result = sandbox.execute(
            self.python_command("print('done')")
        )

        assert result.duration_seconds >= 0


class TestSandboxLifecycle:
    def test_context_manager(self, workspace: Path) -> None:
        with SandboxManager(SandboxConfig(workspace=workspace)) as manager:
            assert manager.workspace == workspace

    def test_cleanup_without_processes(
        self,
        sandbox: SandboxManager,
    ) -> None:
        sandbox.cleanup()

        assert not sandbox._active_processes

    def test_multiple_cleanup_calls(
        self,
        sandbox: SandboxManager,
    ) -> None:
        sandbox.cleanup()
        sandbox.cleanup()

        assert not sandbox._active_processes
