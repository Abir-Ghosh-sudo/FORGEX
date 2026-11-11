
"""Core Git operations for FORGEX."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from git import Repo
from git.exc import GitCommandError

from forgex.tools.git.models import (
    GitBranch,
    GitChangeType,
    GitCommit,
    GitDiff,
    GitFileChange,
    GitOperation,
    GitOperationResult,
    GitStatus,
)
from forgex.tools.git.repository import (
    GitRepositoryManager,
)

logger = logging.getLogger(__name__)


class GitOperationError(Exception):
    """Raised when a Git operation fails."""


class GitOperations:
    """High-level Git operations scoped to a workspace."""

    def __init__(
        self,
        repository_manager: GitRepositoryManager,
        *,
        max_diff_bytes: int = 2_000_000,
        max_history: int = 500,
    ) -> None:
        if max_diff_bytes < 1:
            raise ValueError("max_diff_bytes must be positive.")
        if max_history < 1:
            raise ValueError("max_history must be positive.")

        self.repositories = repository_manager
        self.max_diff_bytes = max_diff_bytes
        self.max_history = max_history

    def status(self, path: Path | str = ".") -> GitStatus:
        repo = self.repositories.discover(path)

        try:
            changes: list[GitFileChange] = []

            for item in repo.index.diff("HEAD"):
                changes.append(
                    GitFileChange(
                        path=item.a_path or item.b_path or "",
                        change_type=self._change_type(item),
                        staged=True,
                        old_path=item.rename_from,
                    )
                )

            for item in repo.index.diff(None):
                changes.append(
                    GitFileChange(
                        path=item.a_path or item.b_path or "",
                        change_type=self._change_type(item),
                        staged=False,
                        old_path=item.rename_from,
                    )
                )

            for item in repo.untracked_files:
                changes.append(
                    GitFileChange(
                        path=item,
                        change_type=GitChangeType.UNTRACKED,
                    )
                )

            try:
                branch = repo.active_branch.name
                detached = False
            except TypeError:
                branch = None
                detached = True

            upstream = None
            ahead = 0
            behind = 0

            if not detached:
                try:
                    tracking = repo.active_branch.tracking_branch()
                    if tracking is not None:
                        upstream = tracking.name
                        ahead = len(list(repo.iter_commits(f"{tracking.name}..HEAD")))
                        behind = len(list(repo.iter_commits(f"HEAD..{tracking.name}")))
                except (GitCommandError, ValueError):
                    pass

            return GitStatus(
                repository_root=Path(repo.working_tree_dir),
                branch=branch,
                is_dirty=repo.is_dirty(untracked_files=True),
                is_detached=detached,
                ahead=ahead,
                behind=behind,
                changes=tuple(changes),
                has_conflicts=bool(repo.index.unmerged_blobs()),
                upstream=upstream,
            )

        except GitCommandError as exc:
            raise GitOperationError("Unable to inspect Git status.") from exc

    def branches(
        self,
        path: Path | str = ".",
        *,
        include_remote: bool = False,
    ) -> tuple[GitBranch, ...]:
        repo = self.repositories.discover(path)

        result = [
            GitBranch(
                name=branch.name,
                is_current=branch == repo.active_branch
                if not repo.head.is_detached
                else False,
                is_remote=False,
                upstream=(
                    branch.tracking_branch().name
                    if branch.tracking_branch()
                    else None
                ),
                last_commit=branch.commit.hexsha,
            )
            for branch in repo.branches
        ]

        if include_remote:
            result.extend(
                GitBranch(
                    name=reference.name,
                    is_remote=True,
                    last_commit=reference.commit.hexsha,
                )
                for reference in repo.remote().refs
                if repo.remotes
            )

        return tuple(result)

    def create_branch(
        self,
        name: str,
        path: Path | str = ".",
        *,
        checkout: bool = True,
    ) -> GitBranch:
        self._validate_branch_name(name)
        repo = self.repositories.discover(path)

        try:
            if name in [branch.name for branch in repo.branches]:
                raise GitOperationError(
                    f"Branch already exists: {name}"
                )

            branch = repo.create_head(name)

            if checkout:
                branch.checkout()

            return GitBranch(
                name=branch.name,
                is_current=checkout,
                last_commit=branch.commit.hexsha,
            )

        except GitCommandError as exc:
            raise GitOperationError(
                f"Could not create branch: {name}"
            ) from exc

    def checkout(
        self,
        branch_name: str,
        path: Path | str = ".",
    ) -> GitBranch:
        repo = self.repositories.discover(path)

        if repo.is_dirty(untracked_files=True):
            raise GitOperationError(
                "Cannot checkout with uncommitted changes. "
                "Commit or stash changes first."
            )

        try:
            branch = repo.heads[branch_name]
            branch.checkout()

            return GitBranch(
                name=branch.name,
                is_current=True,
                last_commit=branch.commit.hexsha,
            )

        except (IndexError, GitCommandError) as exc:
            raise GitOperationError(
                f"Cannot checkout branch: {branch_name}"
            ) from exc

    def delete_branch(
        self,
        name: str,
        path: Path | str = ".",
        *,
        force: bool = False,
    ) -> GitOperationResult:
        repo = self.repositories.discover(path)

        if not force and repo.active_branch.name == name:
            raise GitOperationError(
                "Cannot delete the currently checked-out branch."
            )

        try:
            branch = repo.heads[name]
            repo.delete_head(branch, force=force)

            return self._result(
                GitOperation.DELETE_BRANCH,
                True,
                f"Deleted branch {name}.",
                repo,
            )

        except (IndexError, GitCommandError) as exc:
            raise GitOperationError(
                f"Could not delete branch: {name}"
            ) from exc

    def diff(
        self,
        path: Path | str = ".",
        *,
        staged: bool = False,
        target: str | None = None,
    ) -> GitDiff:
        repo = self.repositories.discover(path)

        try:
            if target is not None:
                self._validate_revision(target)
                diff_index = repo.commit(target).diff(repo.head.commit)
            elif staged:
                diff_index = repo.index.diff("HEAD")
            else:
                diff_index = repo.index.diff(None)

            patches: list[str] = []
            insertions = 0
            deletions = 0
            is_binary = False

            for item in diff_index:
                if item.diff is None:
                    continue

                raw = item.diff

                if isinstance(raw, bytes):
                    try:
                        patch = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        is_binary = True
                        continue
                else:
                    patch = str(raw)

                patches.append(patch)

                for line in patch.splitlines():
                    if line.startswith("+++") or line.startswith("---"):
                        continue
                    if line.startswith("+"):
                        insertions += 1
                    elif line.startswith("-"):
                        deletions += 1

            combined = "\n".join(patches)
            encoded = combined.encode("utf-8")
            truncated = len(encoded) > self.max_diff_bytes

            if truncated:
                combined = encoded[:self.max_diff_bytes].decode(
                    "utf-8",
                    errors="ignore",
                )

            return GitDiff(
                diff_text=combined,
                files_changed=len(diff_index),
                insertions=insertions,
                deletions=deletions,
                is_binary=is_binary,
                truncated=truncated,
            )

        except (GitCommandError, ValueError) as exc:
            raise GitOperationError("Could not generate Git diff.") from exc

    def stage(
        self,
        paths: Sequence[str],
        path: Path | str = ".",
    ) -> GitOperationResult:
        repo = self.repositories.discover(path)
        self._validate_paths(paths)

        try:
            repo.index.add(list(paths))
            return self._result(
                GitOperation.ADD,
                True,
                f"Staged {len(paths)} path(s).",
                repo,
            )
        except (GitCommandError, OSError) as exc:
            raise GitOperationError("Could not stage files.") from exc

    def unstage(
        self,
        paths: Sequence[str],
        path: Path | str = ".",
    ) -> GitOperationResult:
        repo = self.repositories.discover(path)
        self._validate_paths(paths)

        try:
            repo.index.reset(paths=list(paths))
            return self._result(
                GitOperation.RESTORE,
                True,
                f"Unstaged {len(paths)} path(s).",
                repo,
            )
        except GitCommandError as exc:
            raise GitOperationError("Could not unstage files.") from exc

    def commit(
        self,
        message: str,
        path: Path | str = ".",
        *,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> GitCommit:
        if not message.strip():
            raise ValueError("Commit message cannot be empty.")

        repo = self.repositories.discover(path)

        if not repo.index.diff("HEAD") and not repo.untracked_files:
            raise GitOperationError("Nothing to commit.")

        try:
            commit = repo.index.commit(
                message,
                author=(
                    self._actor(author_name, author_email)
                    if author_name and author_email
                    else None
                ),
            )

            return self._commit_model(commit)

        except GitCommandError as exc:
            raise GitOperationError("Git commit failed.") from exc

    def history(
        self,
        path: Path | str = ".",
        *,
        limit: int = 20,
        revision: str = "HEAD",
    ) -> tuple[GitCommit, ...]:
        if not 1 <= limit <= self.max_history:
            raise ValueError(
                f"limit must be between 1 and {self.max_history}."
            )

        self._validate_revision(revision)
        repo = self.repositories.discover(path)

        try:
            return tuple(
                self._commit_model(commit)
                for commit in repo.iter_commits(revision, max_count=limit)
            )
        except GitCommandError as exc:
            raise GitOperationError("Could not read Git history.") from exc

    def stash(
        self,
        path: Path | str = ".",
        *,
        message: str | None = None,
        include_untracked: bool = False,
    ) -> GitOperationResult:
        repo = self.repositories.discover(path)

        try:
            repo.git.stash(
                "push",
                *(["--include-untracked"] if include_untracked else []),
                *(["-m", message] if message else []),
            )

            return self._result(
                GitOperation.STASH,
                True,
                "Git stash operation completed.",
                repo,
            )
        except GitCommandError as exc:
            raise GitOperationError("Git stash failed.") from exc

    def stash_pop(
        self,
        path: Path | str = ".",
        *,
        index: int = 0,
    ) -> GitOperationResult:
        if index < 0:
            raise ValueError("Stash index cannot be negative.")

        repo = self.repositories.discover(path)

        try:
            repo.git.stash("pop", f"stash@{{{index}}}")
            return self._result(
                GitOperation.STASH_POP,
                True,
                "Stash restored.",
                repo,
            )
        except GitCommandError as exc:
            raise GitOperationError("Could not restore stash.") from exc

    @staticmethod
    def _change_type(item) -> GitChangeType:
        if item.renamed:
            return GitChangeType.RENAMED
        if item.deleted_file:
            return GitChangeType.DELETED
        if item.new_file:
            return GitChangeType.ADDED
        if item.a_blob is None:
            return GitChangeType.ADDED
        return GitChangeType.MODIFIED

    @staticmethod
    def _validate_branch_name(name: str) -> None:
        if (
            not isinstance(name, str)
            or not name.strip()
            or name.startswith("-")
            or "\x00" in name
            or name.startswith("/")
            or name.endswith("/")
            or ".." in name
            or " " in name
            or name.endswith(".")
            or name.endswith(".lock")
            or "//" in name
            or "@{" in name
            or name == "@"
        ):
            raise ValueError("Invalid Git branch name.")

    @staticmethod
    def _validate_revision(revision: str) -> None:
        if (
            not isinstance(revision, str)
            or not revision.strip()
            or revision.startswith("-")
            or "\x00" in revision
        ):
            raise ValueError("Invalid Git revision.")

    @staticmethod
    def _validate_paths(paths: Sequence[str]) -> None:
        if not paths:
            raise ValueError("At least one path is required.")

        for path in paths:
            candidate = Path(path)

            if (
                not isinstance(path, str)
                or not path.strip()
                or candidate.is_absolute()
                or "\x00" in path
                or ".." in candidate.parts
            ):
                raise ValueError(f"Invalid Git path: {path!r}")

    @staticmethod
    def _actor(name: str, email: str):
        from git import Actor
        return Actor(name, email)

    @staticmethod
    def _commit_model(commit) -> GitCommit:
        return GitCommit(
            commit_hash=commit.hexsha,
            short_hash=commit.hexsha[:8],
            message=commit.message.strip(),
            author_name=commit.author.name or "",
            author_email=commit.author.email or "",
            committed_at=commit.committed_datetime,
            parents=tuple(parent.hexsha for parent in commit.parents),
        )

    @staticmethod
    def _result(
        operation: GitOperation,
        success: bool,
        message: str,
        repo: Repo,
    ) -> GitOperationResult:
        return GitOperationResult(
            operation=operation,
            success=success,
            message=message,
            repository_root=Path(repo.working_tree_dir),
        )
