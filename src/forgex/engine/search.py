"""Code search engine for FORGEX."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from forgex.engine.parser import (
    ParseResult,
    SourceParser,
    SyntaxNode,
)


class SearchError(RuntimeError):
    """Raised when code search fails."""


@dataclass(frozen=True, slots=True)
class SearchMatch:
    """A single source-code search result."""

    file_path: str
    line: int
    column: int
    text: str
    match_type: str
    symbol: str | None = None


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Aggregated search results."""

    query: str
    matches: tuple[SearchMatch, ...]
    files_searched: int
    truncated: bool = False

    @property
    def total_matches(self) -> int:
        return len(self.matches)


class CodeSearchEngine:
    """Search source files and parsed code symbols."""

    DEFAULT_EXCLUDES = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
    }

    def __init__(
        self,
        workspace: Path,
        parser: SourceParser | None = None,
        *,
        max_file_size: int = 5 * 1024 * 1024,
        max_results: int = 1000,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

        if not self.workspace.is_dir():
            raise SearchError(
                f"Workspace does not exist: {self.workspace}"
            )

        if max_file_size <= 0 or max_results <= 0:
            raise ValueError("Search limits must be positive.")

        self.parser = parser or SourceParser(max_file_size)
        self.max_file_size = max_file_size
        self.max_results = max_results

    def _iter_files(
        self,
        paths: Iterable[str | Path] | None = None,
        extensions: set[str] | None = None,
    ):
        """Iterate through workspace files without following symlinks."""
        roots = (
            [self._resolve_path(path) for path in paths]
            if paths
            else [self.workspace]
        )

        for root in roots:
            if root.is_file():
                candidates = [root]
            else:
                candidates = (
                    path
                    for path in root.rglob("*")
                    if path.is_file()
                    and not path.is_symlink()
                    and not any(
                        part in self.DEFAULT_EXCLUDES
                        for part in path.relative_to(self.workspace).parts
                    )
                )

            for path in candidates:
                if path.is_symlink():
                    continue

                try:
                    path.resolve().relative_to(self.workspace)
                except ValueError:
                    continue

                if extensions and path.suffix.lower() not in extensions:
                    continue

                try:
                    if path.stat().st_size > self.max_file_size:
                        continue
                except OSError:
                    continue

                yield path

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)

        if not candidate.is_absolute():
            candidate = self.workspace / candidate

        resolved = candidate.resolve()

        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise SearchError(
                "Search path must remain inside the workspace."
            ) from exc

        return resolved

    def search_text(
        self,
        query: str,
        *,
        paths: Iterable[str | Path] | None = None,
        extensions: set[str] | None = None,
        case_sensitive: bool = False,
        regex: bool = False,
        max_results: int | None = None,
    ) -> SearchResult:
        """Search literal text or regular expressions in source files."""
        if not query:
            raise ValueError("Search query cannot be empty.")

        limit = max_results or self.max_results

        if limit <= 0:
            raise ValueError("max_results must be positive.")

        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            pattern = re.compile(query if regex else re.escape(query), flags)
        except re.error as exc:
            raise SearchError(f"Invalid regular expression: {exc}") from exc

        matches: list[SearchMatch] = []
        files_searched = 0
        truncated = False

        for path in self._iter_files(paths, extensions):
            files_searched += 1

            try:
                content = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                continue

            for line_number, line in enumerate(
                content.splitlines(),
                start=1,
            ):
                for match in pattern.finditer(line):
                    if len(matches) >= limit:
                        truncated = True
                        break

                    matches.append(
                        SearchMatch(
                            file_path=str(path.relative_to(self.workspace)),
                            line=line_number,
                            column=match.start() + 1,
                            text=line.strip(),
                            match_type="text",
                        )
                    )

                if truncated:
                    break

            if truncated:
                break

        return SearchResult(
            query=query,
            matches=tuple(matches),
            files_searched=files_searched,
            truncated=truncated,
        )

    def search_symbols(
        self,
        query: str,
        *,
        paths: Iterable[str | Path] | None = None,
        case_sensitive: bool = False,
        max_results: int | None = None,
    ) -> SearchResult:
        """Search class, function, and method declarations."""
        if not query:
            raise ValueError("Symbol query cannot be empty.")

        limit = max_results or self.max_results
        needle = query if case_sensitive else query.casefold()

        matches: list[SearchMatch] = []
        files_searched = 0
        truncated = False

        for path in self._iter_files(paths):
            if not self.parser.detect_language(path):
                continue

            files_searched += 1

            try:
                result = self.parser.parse_file(path)
            except Exception:
                continue

            for symbol in self.parser.get_symbols(result):
                name = self._extract_symbol_name(symbol)

                if not name:
                    continue

                candidate = name if case_sensitive else name.casefold()

                if needle not in candidate:
                    continue

                if len(matches) >= limit:
                    truncated = True
                    break

                matches.append(
                    SearchMatch(
                        file_path=str(path.relative_to(self.workspace)),
                        line=symbol.start_line,
                        column=1,
                        text=symbol.text.splitlines()[0].strip(),
                        match_type="symbol",
                        symbol=name,
                    )
                )

            if truncated:
                break

        return SearchResult(
            query=query,
            matches=tuple(matches),
            files_searched=files_searched,
            truncated=truncated,
        )

    @staticmethod
    def _extract_symbol_name(node: SyntaxNode) -> str | None:
        """Extract a declaration name from common syntax nodes."""
        name_types = {
            "identifier",
            "type_identifier",
            "property_identifier",
        }

        for child in node.children:
            if child.node_type in name_types:
                return child.text.strip()

            for nested in child.children:
                if nested.node_type in name_types:
                    return nested.text.strip()

        return None

    def find_references(
        self,
        symbol: str,
        *,
        paths: Iterable[str | Path] | None = None,
        case_sensitive: bool = True,
        max_results: int | None = None,
    ) -> SearchResult:
        """Find textual references to a symbol."""
        return self.search_text(
            symbol,
            paths=paths,
            case_sensitive=case_sensitive,
            max_results=max_results,
        )