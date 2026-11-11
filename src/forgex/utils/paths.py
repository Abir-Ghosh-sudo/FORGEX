"""Cross-platform path utilities for FORGEX."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


class PathValidationError(ValueError):
    """Raised when a path fails validation."""


def normalize_path(
    path: str | Path,
    *,
    strict: bool = False,
) -> Path:
    """Expand user paths and return an absolute normalized path."""

    if not str(path).strip():
        raise PathValidationError("Path cannot be empty.")

    try:
        return Path(path).expanduser().resolve(strict=strict)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PathValidationError(f"Unable to normalize path: {path}") from exc


def validate_directory(
    path: str | Path,
    *,
    create: bool = False,
) -> Path:
    """Validate a directory and optionally create it."""

    directory = normalize_path(path)

    if directory.exists() and not directory.is_dir():
        raise PathValidationError(f"Path exists but is not a directory: {directory}")

    if not directory.exists():
        if not create:
            raise PathValidationError(f"Directory does not exist: {directory}")

        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PathValidationError(f"Unable to create directory: {directory}") from exc

    return directory


def validate_file(
    path: str | Path,
    *,
    must_exist: bool = True,
) -> Path:
    """Validate a file path."""

    file_path = normalize_path(path)

    if must_exist and not file_path.is_file():
        raise PathValidationError(f"File does not exist: {file_path}")

    if file_path.exists() and not file_path.is_file():
        raise PathValidationError(f"Path is not a file: {file_path}")

    return file_path


def is_within_directory(
    path: str | Path,
    directory: str | Path,
) -> bool:
    """Check whether a path resolves inside a directory."""

    target = normalize_path(path)
    root = normalize_path(directory)

    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_workspace_path(
    workspace: str | Path,
    relative_path: str | Path,
    *,
    allow_absolute: bool = False,
) -> Path:
    """Resolve a path while preventing workspace traversal.

    Absolute paths are rejected by default. Symbolic links are resolved
    before the containment check.
    """

    root = validate_directory(workspace)
    candidate = Path(relative_path).expanduser()

    if candidate.is_absolute() and not allow_absolute:
        raise PathValidationError("Absolute paths are not allowed.")

    if not candidate.is_absolute():
        candidate = root / candidate

    resolved = normalize_path(candidate)

    if not is_within_directory(resolved, root):
        raise PathValidationError(f"Path escapes the workspace: {relative_path}")

    return resolved


def ensure_parent_directory(path: str | Path) -> Path:
    """Create the parent directory of a file path."""

    file_path = normalize_path(path)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PathValidationError(f"Unable to create parent directory: {file_path.parent}") from exc

    return file_path


def safe_relative_path(
    path: str | Path,
    root: str | Path,
) -> str:
    """Return a normalized relative path inside a root directory."""

    target = normalize_path(path)
    base = normalize_path(root)

    try:
        return target.relative_to(base).as_posix()
    except ValueError as exc:
        raise PathValidationError(f"Path is outside the specified root: {target}") from exc


def find_files(
    directory: str | Path,
    *,
    patterns: Iterable[str] = ("*",),
    recursive: bool = True,
) -> list[Path]:
    """Find files matching one or more glob patterns."""

    root = validate_directory(directory)
    matches: set[Path] = set()

    for pattern in patterns:
        iterator = root.rglob(pattern) if recursive else root.glob(pattern)

        for candidate in iterator:
            if candidate.is_file():
                matches.add(candidate.resolve())

    return sorted(matches, key=lambda item: item.as_posix().lower())


def get_platform_name() -> str:
    """Return the normalized operating system name."""

    if os.name == "nt":
        return "windows"

    if os.name == "posix":
        return "linux" if Path("/proc").exists() else "unix"

    return os.name


__all__ = [
    "PathValidationError",
    "normalize_path",
    "validate_directory",
    "validate_file",
    "is_within_directory",
    "resolve_workspace_path",
    "ensure_parent_directory",
    "safe_relative_path",
    "find_files",
    "get_platform_name",
]
