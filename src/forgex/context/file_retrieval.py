"""File retrieval utilities for FORGEX context engine."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FileRetriever:
    """Retrieves and inspects files within the workspace."""

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
    EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".o", ".obj"}

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def read(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read a file with optional line range."""
        full = self.workspace / path
        if not full.exists() or not full.is_file():
            raise FileNotFoundError(f"File not found: {full}")
        text = full.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        start = max(0, start_line - 1) if start_line is not None else 0
        end = max(start, end_line) if end_line is not None else len(lines)
        return "".join(lines[start:end])

    def write(
        self,
        path: str,
        content: str,
        *,
        overwrite: bool = False,
    ) -> None:
        """Write content to a file."""
        full = self.workspace / path
        full.parent.mkdir(parents=True, exist_ok=True)
        if full.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {full}")
        full.write_text(content, encoding="utf-8")

    def delete(
        self,
        path: str,
        *,
        permanent: bool = False,
        confirm: bool = False,
    ) -> None:
        """Delete a file within the workspace."""
        full = self.workspace / path
        if not full.exists():
            raise FileNotFoundError(f"File not found: {full}")
        if not permanent:
            raise ValueError("Non-permanent deletion requires trash handling (not implemented).")
        if full.is_dir():
            import shutil

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
        """Find files matching a glob pattern."""
        import fnmatch

        results: list[str] = []
        for p in self.workspace.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(self.workspace))
            if any(part in self.EXCLUDED_DIRS for part in Path(rel).parts):
                continue
            if p.suffix.lower() in self.EXCLUDED_SUFFIXES:
                continue
            match_name = rel if case_sensitive else rel.lower()
            match_pat = pattern if case_sensitive else pattern.lower()
            if fnmatch.fnmatch(match_name, match_pat):
                results.append(rel)
            if max_results and len(results) >= max_results:
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
        """Search file contents for a query string."""
        import fnmatch
        import re

        results: list[str] = []
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(query, flags) if regex else None

        for p in self.workspace.rglob(file_pattern):
            if not p.is_file():
                continue
            rel = str(p.relative_to(self.workspace))
            if any(part in self.EXCLUDED_DIRS for part in Path(rel).parts):
                continue
            if p.suffix.lower() in self.EXCLUDED_SUFFIXES:
                continue
            target_pattern = file_pattern if case_sensitive else file_pattern.lower()
            target_rel = rel if case_sensitive else rel.lower()
            if not fnmatch.fnmatch(target_rel, target_pattern):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            matched = False
            if compiled:
                if compiled.search(text):
                    matched = True
            else:
                search_text = text if case_sensitive else text.lower()
                search_query = query if case_sensitive else query.lower()
                if search_query in search_text:
                    matched = True
            if matched:
                results.append(rel)
            if max_results and len(results) >= max_results:
                break
        return tuple(results)

    def inspect(
        self,
        path: str = ".",
        *,
        recursive: bool = False,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Inspect a directory and return tree metadata."""
        root = self.workspace / path
        if not root.exists() or not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root}")
        return self._build_node(root, depth=0, max_depth=max_depth, recursive=recursive)

    def _build_node(
        self,
        path: Path,
        depth: int,
        max_depth: int,
        recursive: bool,
    ) -> dict[str, Any]:
        name = path.name or str(path)
        node: dict[str, Any] = {
            "name": name,
            "path": str(path.relative_to(self.workspace)),
            "type": "directory" if path.is_dir() else "file",
        }
        if path.is_dir() and depth < max_depth:
            children: list[dict[str, Any]] = []
            try:
                entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                entries = []
            for entry in entries:
                if entry.name in self.EXCLUDED_DIRS:
                    continue
                if entry.suffix.lower() in self.EXCLUDED_SUFFIXES:
                    continue
                if recursive or depth < max_depth:
                    children.append(self._build_node(entry, depth + 1, max_depth, recursive))
            node["children"] = children
        return node

    def build_tree(self, max_depth: int = 3) -> dict[str, Any]:
        """Build a workspace file tree."""
        return self._build_node(self.workspace, depth=0, max_depth=max_depth, recursive=True)

    def inspect_metadata(self, path: str) -> dict[str, Any]:
        """Return metadata for a path."""
        full = self.workspace / path
        if not full.exists():
            raise FileNotFoundError(f"Path not found: {full}")
        stat = full.stat()
        return {
            "path": path,
            "exists": True,
            "is_dir": full.is_dir(),
            "is_file": full.is_file(),
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
        }


__all__ = ["FileRetriever"]
