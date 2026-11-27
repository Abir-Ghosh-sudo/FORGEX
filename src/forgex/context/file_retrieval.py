"""Workspace-confined file retrieval for FORGEX context operations."""

from __future__ import annotations

import fnmatch
import logging
import shutil
from pathlib import Path
from typing import Any

from forgex.tools.filesystem.paths import WorkspacePathResolver

logger = logging.getLogger(__name__)


class FileRetriever:
    """Retrieve and inspect files without allowing workspace escapes."""

    EXCLUDED_DIRS = {
        ".git",
        ".venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "node_modules",
        "build",
        "dist",
        ".idea",
        ".vscode",
    }
    EXCLUDED_SUFFIXES = {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".o",
        ".obj",
    }

    def __init__(self, workspace: Path) -> None:
        self._resolver = WorkspacePathResolver(workspace)
        self.workspace = self._resolver.workspace

    def _resolve(self, path: str, *, must_exist: bool = False):
        return self._resolver.resolve(path, must_exist=must_exist)

    def read(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read a workspace file with optional one-based line range."""
        resolved = self._resolver.resolve(path, expected_type="file")
        if not resolved.exists:
            raise FileNotFoundError(path)
        if start_line is not None and start_line < 1:
            raise ValueError("start_line must be at least 1.")
        if end_line is not None and end_line < 1:
            raise ValueError("end_line must be at least 1.")
        if start_line is not None and end_line is not None and end_line < start_line:
            raise ValueError("end_line cannot precede start_line.")

        text = resolved.absolute.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        start = start_line - 1 if start_line is not None else 0
        end = end_line if end_line is not None else len(lines)
        return "".join(lines[start:end])

    def write(
        self,
        path: str,
        content: str,
        *,
        overwrite: bool = False,
    ) -> None:
        """Write a file only inside the workspace."""
        resolved = self._resolver.resolve(path)
        full = resolved.absolute
        if full.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {full}")
        if full.exists() and not full.is_file():
            raise IsADirectoryError(f"Not a regular file: {full}")
        full.parent.mkdir(parents=True, exist_ok=True)
        # Re-resolve after creating parent directories to catch symlink races
        # and symlinked parent components before writing.
        checked = self._resolver.resolve(path)
        if checked.absolute != full:
            raise OSError("Path changed during write.")
        full.write_text(content, encoding="utf-8")

    def delete(
        self,
        path: str,
        *,
        permanent: bool = False,
        confirm: bool = False,
    ) -> None:
        """Delete a workspace file; permanent deletion requires confirmation."""
        if not permanent:
            raise ValueError("Non-permanent deletion requires trash handling (not implemented).")
        if not confirm:
            raise PermissionError("Permanent deletion requires confirm=True.")
        resolved = self._resolver.resolve(path, must_exist=True)
        full = resolved.absolute
        if full == self.workspace:
            raise PermissionError("The workspace root cannot be deleted.")
        if full.is_dir():
            shutil.rmtree(full)
        else:
            full.unlink()

    def find(
        self,
        pattern: str,
        *,
        case_sensitive: bool = False,
        max_results: int | None = None,
    ) -> tuple[str, ...]:
        """Find files matching a glob pattern, skipping generated directories."""
        results: list[str] = []
        for path in self.workspace.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.workspace).as_posix()
            if any(part in self.EXCLUDED_DIRS for part in Path(rel).parts):
                continue
            if path.suffix.lower() in self.EXCLUDED_SUFFIXES:
                continue
            candidate = rel if case_sensitive else rel.lower()
            target = pattern if case_sensitive else pattern.lower()
            if fnmatch.fnmatch(candidate, target):
                results.append(rel)
                if max_results is not None and len(results) >= max_results:
                    break
        return tuple(results)

    def search_content(
        self,
        query: str,
        *,
        file_pattern: str = "*",
        case_sensitive: bool = False,
        regex: bool = False,
        max_results: int | None = None,
    ) -> tuple[str, ...]:
        """Search workspace text files for a query."""
        import re

        results: list[str] = []
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(query, flags) if regex else None

        for path in self.workspace.rglob(file_pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(self.workspace).as_posix()
            if any(part in self.EXCLUDED_DIRS for part in Path(rel).parts):
                continue
            if path.suffix.lower() in self.EXCLUDED_SUFFIXES:
                continue
            target_pattern = file_pattern if case_sensitive else file_pattern.lower()
            target_rel = rel if case_sensitive else rel.lower()
            if not fnmatch.fnmatch(target_rel, target_pattern):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if (
                compiled.search(text)
                if compiled
                else (query in text if case_sensitive else query.lower() in text.lower())
            ):
                results.append(rel)
                if max_results is not None and len(results) >= max_results:
                    break
        return tuple(results)

    def inspect(
        self,
        path: str = ".",
        *,
        recursive: bool = False,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Inspect a workspace directory with bounded recursion depth."""
        if max_depth < 0:
            raise ValueError("max_depth cannot be negative.")
        resolved = self._resolver.resolve(path, must_exist=True, expected_type="directory")
        return self._build_node(
            resolved.absolute,
            depth=0,
            max_depth=max_depth,
            recursive=recursive,
        )

    def _build_node(
        self,
        path: Path,
        depth: int,
        max_depth: int,
        recursive: bool,
    ) -> dict[str, Any]:
        node: dict[str, Any] = {
            "name": path.name or str(path),
            "path": "." if path == self.workspace else path.relative_to(self.workspace).as_posix(),
            "type": "directory" if path.is_dir() else "file",
        }
        if path.is_dir() and depth < max_depth:
            children: list[dict[str, Any]] = []
            try:
                entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                entries = []
            for entry in entries:
                if (
                    entry.name in self.EXCLUDED_DIRS
                    or entry.suffix.lower() in self.EXCLUDED_SUFFIXES
                ):
                    continue
                if entry.is_symlink():
                    continue
                if recursive or depth < max_depth:
                    children.append(self._build_node(entry, depth + 1, max_depth, recursive))
            node["children"] = children
        return node

    def build_tree(self, max_depth: int = 3) -> dict[str, Any]:
        """Build a workspace file tree."""
        return self.inspect(".", max_depth=max_depth, recursive=True)

    def inspect_metadata(self, path: str) -> dict[str, Any]:
        """Return metadata for a workspace path."""
        resolved = self._resolver.resolve(path, must_exist=True)
        stat = resolved.absolute.stat()
        return {
            "path": resolved.relative.as_posix(),
            "exists": True,
            "is_dir": resolved.is_directory,
            "is_file": resolved.is_file,
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
        }


__all__ = ["FileRetriever"]
