"""Workspace-safe path resolution for FORGEX filesystem tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PathSecurityError(Exception):
    """Raised when a path violates workspace security boundaries."""


class InvalidPathError(PathSecurityError):
    """Raised when a path is malformed or invalid."""


class WorkspaceEscapeError(PathSecurityError):
    """Raised when a path escapes the configured workspace."""


@dataclass(frozen=True, slots=True)
class ResolvedPath:
    """A validated filesystem path."""

    original: str
    absolute: Path
    relative: Path
    exists: bool
    is_file: bool
    is_directory: bool
    is_symlink: bool


class WorkspacePathResolver:
    """Resolve and validate paths within a workspace.

    All paths are resolved against the workspace root. Existing symlinks
    are resolved before containment checks to prevent symlink traversal.
    """

    def __init__(
        self,
        workspace: str | Path,
        *,
        allow_absolute_paths: bool = False,
        allow_symlinks: bool = False,
    ) -> None:
        root = Path(workspace).expanduser()

        try:
            root = root.resolve(strict=True)
        except OSError as exc:
            raise InvalidPathError(f"Workspace does not exist: {root}") from exc

        if not root.is_dir():
            raise InvalidPathError(f"Workspace must be a directory: {root}")

        self._workspace = root
        self._allow_absolute_paths = allow_absolute_paths
        self._allow_symlinks = allow_symlinks

    @property
    def workspace(self) -> Path:
        """Return the canonical workspace root."""
        return self._workspace

    def resolve(
        self,
        value: str | Path,
        *,
        must_exist: bool = False,
        expected_type: str | None = None,
    ) -> ResolvedPath:
        """Resolve a path and enforce workspace containment."""

        if isinstance(value, str):
            if not value or not value.strip():
                raise InvalidPathError("Path cannot be empty.")
            if "\x00" in value:
                raise InvalidPathError("Path contains a null byte.")
            candidate = Path(value)
        elif isinstance(value, Path):
            candidate = value
        else:
            raise TypeError("Path must be a string or pathlib.Path.")

        if candidate.is_absolute() and not self._allow_absolute_paths:
            raise InvalidPathError("Absolute paths are not permitted.")

        if not candidate.is_absolute():
            candidate = self._workspace / candidate

        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise InvalidPathError(f"Unable to resolve path: {value}") from exc

        self._ensure_inside_workspace(resolved)

        if not self._allow_symlinks:
            self._check_symlink_components(candidate)

        exists = resolved.exists()
        is_file = resolved.is_file() if exists else False
        is_directory = resolved.is_dir() if exists else False
        is_symlink = candidate.is_symlink()

        if must_exist and not exists:
            raise InvalidPathError(f"Path does not exist: {resolved}")

        if expected_type == "file" and exists and not is_file:
            raise InvalidPathError(f"Expected a file: {resolved}")

        if expected_type == "directory" and exists and not is_directory:
            raise InvalidPathError(f"Expected a directory: {resolved}")

        if expected_type not in (None, "file", "directory"):
            raise ValueError("expected_type must be 'file', 'directory', or None.")

        try:
            relative = resolved.relative_to(self._workspace)
        except ValueError as exc:
            raise WorkspaceEscapeError(f"Path escapes workspace: {value}") from exc

        return ResolvedPath(
            original=str(value),
            absolute=resolved,
            relative=relative,
            exists=exists,
            is_file=is_file,
            is_directory=is_directory,
            is_symlink=is_symlink,
        )

    def _ensure_inside_workspace(self, path: Path) -> None:
        """Reject paths outside the workspace."""

        try:
            path.relative_to(self._workspace)
        except ValueError as exc:
            raise WorkspaceEscapeError(f"Path escapes workspace: {path}") from exc

    def _check_symlink_components(self, candidate: Path) -> None:
        """Reject symlinks in existing path components."""

        try:
            relative = candidate.relative_to(self._workspace)
        except ValueError as exc:
            raise WorkspaceEscapeError(f"Path escapes workspace: {candidate}") from exc

        current = self._workspace

        for component in relative.parts:
            if component in ("", ".", ".."):
                raise InvalidPathError("Invalid path component.")

            current = current / component

            try:
                if current.is_symlink():
                    raise PathSecurityError(f"Symlinks are not permitted: {current}")
            except OSError as exc:
                raise InvalidPathError(f"Unable to inspect path: {current}") from exc

    def is_within_workspace(self, value: str | Path) -> bool:
        """Return whether a path can be safely resolved in this workspace."""

        try:
            self.resolve(value)
            return True
        except (PathSecurityError, OSError, ValueError, TypeError):
            return False
