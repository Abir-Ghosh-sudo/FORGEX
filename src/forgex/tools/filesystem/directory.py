"""Workspace directory inspection utilities for FORGEX."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.paths import WorkspacePathResolver

logger = logging.getLogger(__name__)


class DirectoryOperationError(Exception):
    """Base exception for directory inspection failures."""


@dataclass(frozen=True, slots=True)
class DirectoryEntry:
    """Metadata for one directory entry."""

    name: str
    path: Path
    relative_path: str
    is_directory: bool
    is_file: bool
    is_symlink: bool
    size_bytes: int | None
    extension: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "relative_path": self.relative_path,
            "is_directory": self.is_directory,
            "is_file": self.is_file,
            "is_symlink": self.is_symlink,
            "size_bytes": self.size_bytes,
            "extension": self.extension,
        }


@dataclass(frozen=True, slots=True)
class DirectoryListing:
    """Result of listing a directory."""

    root: Path
    entries: tuple[DirectoryEntry, ...]
    total_entries: int
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "entries": [entry.to_dict() for entry in self.entries],
            "total_entries": self.total_entries,
            "truncated": self.truncated,
        }


class DirectoryInspector:
    """Inspect directories within a validated workspace."""

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        ignore_patterns: tuple[str, ...] = (
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            ".forgex-trash",
        ),
        max_entries: int = 10_000,
    ) -> None:
        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be a WorkspacePathResolver.")

        if max_entries <= 0:
            raise ValueError("max_entries must be positive.")

        self._resolver = resolver
        self._ignore_patterns = frozenset(ignore_patterns)
        self._max_entries = max_entries

    def list_directory(
        self,
        path: str | Path = ".",
        *,
        recursive: bool = False,
        include_hidden: bool = False,
        include_directories: bool = True,
        include_files: bool = True,
        max_depth: int = 5,
        max_entries: int | None = None,
    ) -> DirectoryListing:
        """List directory entries with configurable traversal."""

        if not include_directories and not include_files:
            raise ValueError("At least one entry type must be included.")

        if max_depth < 0:
            raise ValueError("max_depth cannot be negative.")

        limit = self._max_entries if max_entries is None else max_entries

        if limit <= 0:
            raise ValueError("max_entries must be positive.")

        limit = min(limit, self._max_entries)

        resolved = self._resolver.resolve(
            path,
            must_exist=True,
            expected_type="directory",
        )

        root = resolved.absolute
        entries: list[DirectoryEntry] = []
        total = 0
        truncated = False

        def visit(directory: Path, depth: int) -> None:
            nonlocal total, truncated

            if truncated:
                return

            try:
                children = sorted(
                    directory.iterdir(),
                    key=lambda item: (
                        not item.is_dir() if not item.is_symlink() else True,
                        item.name.casefold(),
                    ),
                )
            except OSError as exc:
                raise DirectoryOperationError(f"Cannot inspect directory: {directory}") from exc

            for child in children:
                if child.is_symlink():
                    continue

                if not include_hidden and child.name.startswith("."):
                    continue

                if child.name in self._ignore_patterns:
                    continue

                is_directory = child.is_dir()
                is_file = child.is_file()

                if is_directory and not include_directories or is_file and not include_files:
                    pass
                elif is_directory or is_file:
                    total += 1

                    if len(entries) >= limit:
                        truncated = True
                        return

                    try:
                        relative = child.relative_to(self._resolver.workspace).as_posix()

                        size = child.stat().st_size if is_file else None

                        entries.append(
                            DirectoryEntry(
                                name=child.name,
                                path=child,
                                relative_path=relative,
                                is_directory=is_directory,
                                is_file=is_file,
                                is_symlink=False,
                                size_bytes=size,
                                extension=(child.suffix.lower() or None if is_file else None),
                            )
                        )
                    except OSError:
                        logger.debug(
                            "Could not inspect directory entry: %s",
                            child,
                            exc_info=True,
                        )

                if recursive and is_directory and depth < max_depth:
                    visit(child, depth + 1)

                if truncated:
                    return

        visit(root, 0)

        return DirectoryListing(
            root=root,
            entries=tuple(entries),
            total_entries=total,
            truncated=truncated,
        )

    def tree(
        self,
        path: str | Path = ".",
        *,
        max_depth: int = 3,
        include_hidden: bool = False,
    ) -> str:
        """Generate a human-readable directory tree."""

        if max_depth < 0:
            raise ValueError("max_depth cannot be negative.")

        resolved = self._resolver.resolve(
            path,
            must_exist=True,
            expected_type="directory",
        )

        root = resolved.absolute
        lines = [root.name or str(root)]
        count = 0

        def render(directory: Path, prefix: str, depth: int) -> None:
            nonlocal count

            if depth >= max_depth:
                return

            try:
                children = sorted(
                    (
                        child
                        for child in directory.iterdir()
                        if not child.is_symlink()
                        and (include_hidden or not child.name.startswith("."))
                        and child.name not in self._ignore_patterns
                        and (child.is_file() or child.is_dir())
                    ),
                    key=lambda item: (
                        not item.is_dir(),
                        item.name.casefold(),
                    ),
                )
            except OSError as exc:
                raise DirectoryOperationError(f"Cannot build tree for: {directory}") from exc

            for index, child in enumerate(children):
                count += 1

                if count > self._max_entries:
                    lines.append(prefix + "└── ... (entry limit reached)")
                    return

                last = index == len(children) - 1
                connector = "└── " if last else "├── "
                suffix = "/" if child.is_dir() else ""

                lines.append(prefix + connector + child.name + suffix)

                if child.is_dir():
                    extension = "    " if last else "│   "
                    render(child, prefix + extension, depth + 1)

                if count >= self._max_entries:
                    return

        render(root, "", 0)
        return "\n".join(lines)
