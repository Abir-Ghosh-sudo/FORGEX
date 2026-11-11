"""Safe Git manager for FORGEX.

Wraps GitPython and existing tools.git operations with safety checks,
branch management, commit, rollback, and recovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forgex.tools.git import (
    GitOperations,
    GitRepositoryManager,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GitOperationResult:
    """Result of a FORGEX Git operation."""

    success: bool
    operation: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class GitSafetyChecker:
    """Checks Git operations for safety before execution."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def is_safe_branch(self, branch_name: str) -> bool:
        """Check if a branch name is safe."""
        dangerous = {"main", "master", "production", "prod"}
        return branch_name not in dangerous

    def is_safe_commit_message(self, message: str) -> bool:
        """Check if a commit message is safe."""
        return bool(message and len(message.strip()) >= 3 and len(message) <= 200)

    def is_path_within_workspace(self, path: str) -> bool:
        """Check if a path is within the workspace."""
        try:
            resolved = (self.workspace / path).resolve()
            return str(resolved).startswith(str(self.workspace.resolve()))
        except Exception:
            return False


class GitManager:
    """Manages Git operations with safety for FORGEX."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.safety = GitSafetyChecker(self.workspace)
        try:
            self._repo_manager = GitRepositoryManager(self.workspace)
            self._operations = GitOperations(self.workspace)
        except Exception as exc:
            logger.debug("Git tools initialization deferred: %s", exc)
            self._repo_manager = None
            self._operations = None

    def is_git_repo(self) -> bool:
        """Check if workspace is a Git repository."""
        return (self.workspace / ".git").exists()

    def init_repo(self) -> GitOperationResult:
        """Initialize a Git repository."""
        if not self.safety.is_path_within_workspace("."):
            return GitOperationResult(False, "init", "Workspace path unsafe.")
        try:
            if self._repo_manager:
                self._repo_manager.init()
            else:
                import subprocess

                subprocess.run(
                    ["git", "init"],
                    cwd=self.workspace,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            return GitOperationResult(True, "init", "Git repository initialized.")
        except Exception as exc:
            return GitOperationResult(False, "init", str(exc))

    def get_status(self) -> GitOperationResult:
        """Get Git status."""
        try:
            if self._operations:
                status = self._operations.status()
                return GitOperationResult(
                    True, "status", "Git status retrieved.", data={"status": str(status)}
                )
            import subprocess

            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )
            return GitOperationResult(
                True, "status", "Git status retrieved.", data={"status": result.stdout}
            )
        except Exception as exc:
            return GitOperationResult(False, "status", str(exc))

    def create_branch(self, branch_name: str) -> GitOperationResult:
        """Create a new branch safely."""
        if not self.safety.is_safe_branch(branch_name):
            return GitOperationResult(
                False, "create_branch", f"Branch '{branch_name}' is protected."
            )
        try:
            import subprocess

            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.workspace,
                check=True,
                capture_output=True,
                text=True,
            )
            return GitOperationResult(True, "create_branch", f"Branch '{branch_name}' created.")
        except Exception as exc:
            return GitOperationResult(False, "create_branch", str(exc))

    def commit(self, message: str, files: list[str] | None = None) -> GitOperationResult:
        """Commit changes safely."""
        if not self.safety.is_safe_commit_message(message):
            return GitOperationResult(False, "commit", "Unsafe commit message.")
        try:
            import subprocess

            if files:
                for f in files:
                    if not self.safety.is_path_within_workspace(f):
                        return GitOperationResult(False, "commit", f"File outside workspace: {f}")
                    subprocess.run(
                        ["git", "add", f],
                        cwd=self.workspace,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
            else:
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=self.workspace,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.workspace,
                check=True,
                capture_output=True,
                text=True,
            )
            return GitOperationResult(True, "commit", f"Committed: {message}")
        except Exception as exc:
            return GitOperationResult(False, "commit", str(exc))

    def rollback(self, commit_ref: str = "HEAD~1") -> GitOperationResult:
        """Rollback to a previous commit."""
        try:
            import subprocess

            subprocess.run(
                ["git", "reset", "--hard", commit_ref],
                cwd=self.workspace,
                check=True,
                capture_output=True,
                text=True,
            )
            return GitOperationResult(True, "rollback", f"Rolled back to {commit_ref}.")
        except Exception as exc:
            return GitOperationResult(False, "rollback", str(exc))

    def get_diff(self) -> GitOperationResult:
        """Get working tree diff."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "diff"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )
            return GitOperationResult(True, "diff", "Diff retrieved.", data={"diff": result.stdout})
        except Exception as exc:
            return GitOperationResult(False, "diff", str(exc))


__all__ = ["GitManager", "GitOperationResult", "GitSafetyChecker"]
