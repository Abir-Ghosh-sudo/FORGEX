"""Shared data models for FORGEX Git tools."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


class GitOperation(StrEnum):
    STATUS = "status"
    INIT = "init"
    BRANCH = "branch"
    CHECKOUT = "checkout"
    CREATE_BRANCH = "create_branch"
    DELETE_BRANCH = "delete_branch"
    DIFF = "diff"
    ADD = "add"
    COMMIT = "commit"
    LOG = "log"
    RESET = "reset"
    STASH = "stash"
    STASH_POP = "stash_pop"
    RESTORE = "restore"
    CLONE = "clone"
    PULL = "pull"
    PUSH = "push"
    MERGE = "merge"
    TAG = "tag"


class GitChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    UNTRACKED = "untracked"
    CONFLICTED = "conflicted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GitFileChange:
    path: str
    change_type: GitChangeType
    staged: bool = False
    old_path: str | None = None

    def __post_init__(self) -> None:
        if not self.path or "\x00" in self.path:
            raise ValueError("Git file path must be non-empty.")

        if not isinstance(self.change_type, GitChangeType):
            object.__setattr__(
                self,
                "change_type",
                GitChangeType(self.change_type),
            )

        if self.old_path is not None and "\x00" in self.old_path:
            raise ValueError("Invalid old_path.")

        if not isinstance(self.staged, bool):
            raise TypeError("staged must be bool.")


@dataclass(frozen=True, slots=True)
class GitStatus:
    repository_root: Path
    branch: str | None
    is_dirty: bool
    is_detached: bool = False
    ahead: int = 0
    behind: int = 0
    changes: tuple[GitFileChange, ...] = ()
    has_conflicts: bool = False
    upstream: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "repository_root",
            Path(self.repository_root).expanduser().resolve(),
        )

        if self.ahead < 0 or self.behind < 0:
            raise ValueError("ahead and behind cannot be negative.")

        object.__setattr__(self, "changes", tuple(self.changes))


@dataclass(frozen=True, slots=True)
class GitBranch:
    name: str
    is_current: bool = False
    is_remote: bool = False
    upstream: str | None = None
    last_commit: str | None = None

    def __post_init__(self) -> None:
        if not self.name or "\x00" in self.name:
            raise ValueError("Branch name must be non-empty.")


@dataclass(frozen=True, slots=True)
class GitCommit:
    commit_hash: str
    short_hash: str
    message: str
    author_name: str
    author_email: str
    committed_at: datetime
    parents: tuple[str, ...] = ()
    branch: str | None = None

    def __post_init__(self) -> None:
        if not self.commit_hash:
            raise ValueError("commit_hash cannot be empty.")

        if not self.short_hash:
            raise ValueError("short_hash cannot be empty.")

        object.__setattr__(self, "parents", tuple(self.parents))


@dataclass(frozen=True, slots=True)
class GitDiff:
    diff_text: str
    files_changed: int
    insertions: int = 0
    deletions: int = 0
    is_binary: bool = False
    truncated: bool = False

    def __post_init__(self) -> None:
        if min(self.files_changed, self.insertions, self.deletions) < 0:
            raise ValueError("Diff statistics cannot be negative.")


@dataclass(frozen=True, slots=True)
class GitOperationResult:
    operation: GitOperation
    success: bool
    message: str
    repository_root: Path | None = None
    data: Any = None
    error: str | None = None
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, GitOperation):
            object.__setattr__(
                self,
                "operation",
                GitOperation(self.operation),
            )

        if self.repository_root is not None:
            object.__setattr__(
                self,
                "repository_root",
                Path(self.repository_root).expanduser().resolve(),
            )

        if not self.operation_id:
            raise ValueError("operation_id cannot be empty.")

        if self.success and self.error is not None:
            raise ValueError("Successful operations cannot contain errors.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "success": self.success,
            "message": self.message,
            "repository_root": (
                str(self.repository_root)
                if self.repository_root is not None
                else None
            ),
            "data": self.data,
            "error": self.error,
            "operation_id": self.operation_id,
            "timestamp": self.timestamp.isoformat(),
        }