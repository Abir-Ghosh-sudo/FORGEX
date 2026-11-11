
"""Git remote and network operations for FORGEX."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from git import Repo
from git.exc import GitCommandError

from forgex.tools.git.models import GitOperation, GitOperationResult
from forgex.tools.git.repository import GitRepositoryManager

logger = logging.getLogger(__name__)


class GitRemoteError(Exception):
    """Raised when a Git remote operation fails."""


class GitRemoteOperations:
    """Manage remote repositories and synchronization."""

    def __init__(
        self,
        repositories: GitRepositoryManager,
        *,
        default_remote: str = "origin",
    ) -> None:
        if not default_remote or "\x00" in default_remote:
            raise ValueError("Invalid default remote name.")

        self.repositories = repositories
        self.default_remote = default_remote

    def list_remotes(
        self,
        path: Path | str = ".",
    ) -> dict[str, str]:
        repo = self.repositories.discover(path)

        return {
            remote.name: remote.url
            for remote in repo.remotes
        }

    def add_remote(
        self,
        name: str,
        url: str,
        path: Path | str = ".",
    ) -> GitOperationResult:
        self._validate_remote_name(name)
        self._validate_url(url)

        repo = self.repositories.discover(path)

        if name in [remote.name for remote in repo.remotes]:
            raise GitRemoteError(f"Remote already exists: {name}")

        try:
            repo.create_remote(name, url)

            return self._result(
                GitOperation.FETCH,
                True,
                f"Remote '{name}' added.",
                repo,
            )
        except GitCommandError as exc:
            raise GitRemoteError("Could not add remote.") from exc

    def remove_remote(
        self,
        name: str,
        path: Path | str = ".",
    ) -> GitOperationResult:
        repo = self.repositories.discover(path)

        try:
            repo.delete_remote(repo.remote(name))

            return self._result(
                GitOperation.FETCH,
                True,
                f"Remote '{name}' removed.",
                repo,
            )
        except (ValueError, GitCommandError) as exc:
            raise GitRemoteError(
                f"Could not remove remote: {name}"
            ) from exc

    def fetch(
        self,
        path: Path | str = ".",
        *,
        remote: str | None = None,
        prune: bool = False,
        tags: bool = False,
    ) -> GitOperationResult:
        repo = self.repositories.discover(path)
        selected = remote or self.default_remote

        try:
            target = repo.remote(selected)
            target.fetch(
                prune=prune,
                tags=tags,
            )

            return self._result(
                GitOperation.FETCH,
                True,
                f"Fetched from '{selected}'.",
                repo,
            )
        except (ValueError, GitCommandError) as exc:
            raise GitRemoteError(
                f"Fetch failed for remote '{selected}'."
            ) from exc

    def pull(
        self,
        path: Path | str = ".",
        *,
        remote: str | None = None,
        branch: str | None = None,
        rebase: bool = False,
    ) -> GitOperationResult:
        repo = self.repositories.discover(path)
        selected = remote or self.default_remote

        if repo.is_dirty(untracked_files=True):
            raise GitRemoteError(
                "Pull blocked: commit or stash local changes first."
            )

        if repo.head.is_detached:
            raise GitRemoteError(
                "Pull is unavailable in detached HEAD state."
            )

        try:
            target = repo.remote(selected)
            refspec = branch or repo.active_branch.name

            if rebase:
                repo.git.pull("--rebase", selected, refspec)
            else:
                target.pull(refspec)

            return self._result(
                GitOperation.PULL,
                True,
                f"Pulled '{refspec}' from '{selected}'.",
                repo,
            )
        except (ValueError, GitCommandError) as exc:
            raise GitRemoteError("Git pull failed.") from exc

    def push(
        self,
        path: Path | str = ".",
        *,
        remote: str | None = None,
        branch: str | None = None,
        set_upstream: bool = False,
        force: bool = False,
    ) -> GitOperationResult:
        repo = self.repositories.discover(path)
        selected = remote or self.default_remote

        if repo.head.is_detached:
            raise GitRemoteError(
                "Push is unavailable in detached HEAD state."
            )

        if repo.is_dirty(untracked_files=True):
            raise GitRemoteError(
                "Push blocked: working tree has uncommitted changes."
            )

        if force:
            raise GitRemoteError(
                "Force push is disabled for safety. "
                "Use an explicit reviewed Git workflow instead."
            )

        try:
            target = repo.remote(selected)
            refspec = branch or repo.active_branch.name

            if set_upstream:
                target.push(
                    refspec,
                    set_upstream=True,
                )
            else:
                target.push(refspec)

            return self._result(
                GitOperation.PUSH,
                True,
                f"Pushed '{refspec}' to '{selected}'.",
                repo,
            )
        except (ValueError, GitCommandError) as exc:
            raise GitRemoteError("Git push failed.") from exc

    def clone(
        self,
        url: str,
        destination: Path | str,
        *,
        branch: str | None = None,
        depth: int | None = None,
    ) -> Repo:
        self._validate_url(url)

        target = self.repositories._resolve_workspace_path(destination)

        if target.exists() and any(target.iterdir()):
            raise GitRemoteError(
                "Clone destination must be empty or nonexistent."
            )

        if depth is not None and depth < 1:
            raise ValueError("Clone depth must be positive.")

        kwargs = {}

        if branch:
            if (
                not branch.strip()
                or branch.startswith("-")
                or "\x00" in branch
            ):
                raise ValueError("Invalid branch name.")
            kwargs["branch"] = branch

        if depth is not None:
            kwargs["depth"] = depth

        try:
            target.parent.mkdir(parents=True, exist_ok=True)

            repo = Repo.clone_from(
                url,
                str(target),
                **kwargs,
            )

            self.repositories._validate_repository(repo)

            logger.info("Cloned repository into %s", target)
            return repo

        except (GitCommandError, OSError, ValueError) as exc:
            raise GitRemoteError("Git clone failed.") from exc

    @staticmethod
    def _validate_remote_name(name: str) -> None:
        if (
            not isinstance(name, str)
            or not name.strip()
            or name.startswith("-")
            or "\x00" in name
            or any(char.isspace() for char in name)
        ):
            raise ValueError("Invalid remote name.")

    @staticmethod
    def _validate_url(url: str) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Remote URL cannot be empty.")

        if "\x00" in url or url.startswith("-"):
            raise ValueError("Invalid remote URL.")

        if url.startswith(("http://", "https://", "ssh://", "git://")):
            parsed = urlparse(url)
            if not parsed.hostname:
                raise ValueError("Remote URL must include a hostname.")
            return

        if url.startswith("git@"):
            if ":" not in url:
                raise ValueError("Invalid SSH Git URL.")
            return

        raise ValueError(
            "Only HTTP(S), SSH, and Git protocol URLs are supported."
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
