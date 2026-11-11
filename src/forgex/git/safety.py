"""Git safety module for FORGEX."""

from __future__ import annotations

from pathlib import Path


class GitSafetyChecker:
    """Placeholder re-exported from git.manager for backward compatibility."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def is_safe_branch(self, branch_name: str) -> bool:
        dangerous = {"main", "master", "production", "prod"}
        return branch_name not in dangerous

    def is_safe_commit_message(self, message: str) -> bool:
        return bool(message and len(message.strip()) >= 3 and len(message) <= 200)

    def is_path_within_workspace(self, path: str) -> bool:
        try:
            resolved = (self.workspace / path).resolve()
            return str(resolved).startswith(str(self.workspace.resolve()))
        except Exception:
            return False


__all__ = ["GitSafetyChecker"]
