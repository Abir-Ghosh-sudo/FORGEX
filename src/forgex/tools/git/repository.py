"""Git repository discovery and validation for FORGEX."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo
from git.exc import GitCommandError

logger = logging.getLogger(__name__)


class GitRepositoryError(Exception):
    """Base exception for Git repository operations."""


class GitRepositoryNotFoundError(GitRepositoryError):
    """Raised when no Git repository can be found."""


class GitRepositorySecurityError(GitRepositoryError):
    """Raised when repository access violates workspace boundaries."""


class GitRepositoryInitializationError(GitRepositoryError):
    """Raised when repository initialization fails."""


@dataclass(frozen=True, slots=True)
class RepositoryInfo:
    root: Path
    git_dir: Path
    working_tree: Path
    branch: str | None
    is_bare: bool
    is_dirty: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).resolve())
        object.__setattr__(self, "git_dir", Path(self.git_dir).resolve())
        object.__setattr__(self, "working_tree", Path(self.working_tree).resolve())


class GitRepositoryManager:
    """Discover, validate, and initialize Git repositories."""

    def __init__(
        self,
        workspace: Path,
        *,
        search_parent_directories: bool = True,
        allow_bare: bool = False,
    ) -> None:
        try:
            root = Path(workspace).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise GitRepositorySecurityError(
                "Workspace does not exist or cannot be resolved."
            ) from exc

        if not root.is_dir():
            raise GitRepositorySecurityError("Workspace must be a directory.")

        self.workspace = root
        self.search_parent_directories = search_parent_directories
        self.allow_bare = allow_bare

    def discover(self, path: Path | str = ".") -> Repo:
        """Find a repository without allowing workspace escape."""

        target = self._resolve_workspace_path(path)

        try:
            repo = Repo(
                str(target),
                search_parent_directories=self.search_parent_directories,
            )
        except (InvalidGitRepositoryError, NoSuchPathError, OSError) as exc:
            raise GitRepositoryNotFoundError(f"No Git repository found for: {target}") from exc

        self._validate_repository(repo)
        return repo

    def get_info(self, path: Path | str = ".") -> RepositoryInfo:
        """Return normalized repository metadata."""

        repo = self.discover(path)

        try:
            working_tree = Path(repo.working_tree_dir).resolve()
            git_dir = Path(repo.git_dir).resolve()

            branch = repo.active_branch.name if not repo.head.is_detached else None

            return RepositoryInfo(
                root=working_tree,
                git_dir=git_dir,
                working_tree=working_tree,
                branch=branch,
                is_bare=repo.bare,
                is_dirty=repo.is_dirty(untracked_files=True),
            )
        except (GitCommandError, TypeError, ValueError) as exc:
            raise GitRepositoryError("Unable to inspect Git repository.") from exc

    def initialize(
        self,
        path: Path | str = ".",
        *,
        initial_branch: str = "main",
    ) -> Repo:
        """Initialize a repository inside the configured workspace."""

        target = self._resolve_workspace_path(path)

        if not initial_branch or "\x00" in initial_branch:
            raise ValueError("Invalid initial branch name.")

        if target.exists() and not target.is_dir():
            raise GitRepositoryInitializationError("Repository target must be a directory.")

        if (target / ".git").exists():
            raise GitRepositoryInitializationError(
                "A Git repository already exists at this location."
            )

        try:
            target.mkdir(parents=True, exist_ok=True)

            repo = Repo.init(
                str(target),
                initial_branch=initial_branch,
            )

            self._validate_repository(repo)
            logger.info("Initialized Git repository at %s", target)
            return repo

        except (GitCommandError, OSError, ValueError) as exc:
            raise GitRepositoryInitializationError(
                f"Could not initialize Git repository: {target}"
            ) from exc

    init = initialize

    def is_repository(self, path: Path | str = ".") -> bool:
        """Check whether a valid repository exists at a path."""

        try:
            self.discover(path)
            return True
        except GitRepositoryNotFoundError:
            return False

    def _resolve_workspace_path(self, path: Path | str) -> Path:
        """Resolve paths while enforcing workspace containment."""

        candidate = Path(path).expanduser()

        if not candidate.is_absolute():
            candidate = self.workspace / candidate

        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(self.workspace)
        except (OSError, ValueError, RuntimeError) as exc:
            raise GitRepositorySecurityError(
                "Git operation cannot access paths outside the workspace."
            ) from exc

        return resolved

    def _validate_repository(self, repo: Repo) -> None:
        """Ensure discovered repositories belong to the workspace."""

        if repo.bare:
            if not self.allow_bare:
                raise GitRepositorySecurityError("Bare repositories are not allowed.")
            return

        if repo.working_tree_dir is None:
            raise GitRepositorySecurityError("Repository has no working tree.")

        try:
            working_tree = Path(repo.working_tree_dir).resolve(strict=True)
            working_tree.relative_to(self.workspace)
        except (OSError, ValueError, RuntimeError) as exc:
            raise GitRepositorySecurityError(
                "Repository working tree is outside the workspace."
            ) from exc
