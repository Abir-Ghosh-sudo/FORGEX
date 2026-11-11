"""Workspace file and content search for FORGEX."""

from __future__ import annotations

import fnmatch
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.paths import WorkspacePathResolver

logger = logging.getLogger(__name__)

DEFAULT_IGNORE_PATTERNS = (
    ".git/**",
    ".venv/**",
    "venv/**",
    "__pycache__/**",
    "node_modules/**",
    ".forgex-trash/**",
    "dist/**",
    "build/**",
    "*.pyc",
    "*.lock",
)

DEFAULT_MAX_FILE_SIZE = 2 * 1024 * 1024


class SearchError(Exception):
    """Base exception for filesystem search failures."""


class InvalidSearchPatternError(SearchError):
    """Raised when a search pattern is invalid."""


@dataclass(frozen=True, slots=True)
class SearchMatch:
    """A single content search match."""

    path: Path
    line_number: int
    column: int
    line: str
    matched_text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "line_number": self.line_number,
            "column": self.column,
            "line": self.line,
            "matched_text": self.matched_text,
        }


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Filesystem search result."""

    query: str
    matches: tuple[SearchMatch, ...]
    files_scanned: int
    files_skipped: int
    truncated: bool

    @property
    def match_count(self) -> int:
        return len(self.matches)

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "matches": [match.to_dict() for match in self.matches],
            "match_count": self.match_count,
            "files_scanned": self.files_scanned,
            "files_skipped": self.files_skipped,
            "truncated": self.truncated,
        }


class FileSearch:
    """Search filenames and text content inside a workspace."""

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        ignore_patterns: tuple[str, ...] = DEFAULT_IGNORE_PATTERNS,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_results: int = 500,
        max_files: int = 20_000,
    ) -> None:
        if max_file_size <= 0 or max_results <= 0 or max_files <= 0:
            raise ValueError("Search limits must be positive.")

        self._resolver = resolver
        self._ignore_patterns = tuple(ignore_patterns)
        self._max_file_size = max_file_size
        self._max_results = max_results
        self._max_files = max_files

    def search_filenames(
        self,
        pattern: str,
        *,
        case_sensitive: bool = False,
        max_results: int | None = None,
    ) -> tuple[Path, ...]:
        """Find files and directories whose relative paths match a pattern."""

        self._validate_pattern(pattern)
        limit = self._validate_limit(max_results)

        results: list[Path] = []

        for path in self._walk_files(include_directories=True):
            relative = path.relative_to(self._resolver.workspace).as_posix()
            candidate = relative if case_sensitive else relative.casefold()
            expected = pattern if case_sensitive else pattern.casefold()

            if fnmatch.fnmatchcase(candidate, expected):
                results.append(path)

                if len(results) >= limit:
                    break

        return tuple(results)

    def search_content(
        self,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        file_pattern: str = "*",
        max_results: int | None = None,
    ) -> SearchResult:
        """Search text content and return line-based matches."""

        self._validate_pattern(query)
        self._validate_pattern(file_pattern)

        limit = self._validate_limit(max_results)

        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            expression = re.compile(query if regex else re.escape(query), flags)
        except re.error as exc:
            raise InvalidSearchPatternError(f"Invalid regular expression: {exc}") from exc

        matches: list[SearchMatch] = []
        files_scanned = 0
        files_skipped = 0
        truncated = False

        for path in self._walk_files():
            relative = path.relative_to(self._resolver.workspace).as_posix()

            if not fnmatch.fnmatchcase(relative, file_pattern):
                continue

            try:
                size = path.stat().st_size

                if size > self._max_file_size:
                    files_skipped += 1
                    continue

                data = path.read_bytes()

                if b"\x00" in data:
                    files_skipped += 1
                    continue

                content = data.decode("utf-8", errors="strict")
                files_scanned += 1

                for line_number, line in enumerate(
                    content.splitlines(),
                    start=1,
                ):
                    for match in expression.finditer(line):
                        matches.append(
                            SearchMatch(
                                path=path,
                                line_number=line_number,
                                column=match.start() + 1,
                                line=line[:1000],
                                matched_text=match.group(0),
                            )
                        )

                        if len(matches) >= limit:
                            truncated = True
                            return SearchResult(
                                query=query,
                                matches=tuple(matches),
                                files_scanned=files_scanned,
                                files_skipped=files_skipped,
                                truncated=truncated,
                            )

            except (OSError, UnicodeDecodeError):
                files_skipped += 1
                logger.debug(
                    "Skipping unreadable search target: %s",
                    path,
                    exc_info=True,
                )

        return SearchResult(
            query=query,
            matches=tuple(matches),
            files_scanned=files_scanned,
            files_skipped=files_skipped,
            truncated=truncated,
        )

    def _walk_files(
        self,
        *,
        include_directories: bool = False,
    ) -> Iterator[Path]:
        """Walk workspace without following symlinks."""

        root = self._resolver.workspace
        visited = 0

        for current, directories, files in __import__("os").walk(
            root,
            topdown=True,
            followlinks=False,
        ):
            current_path = Path(current)

            directories[:] = [
                name
                for name in directories
                if not (current_path / name).is_symlink()
                and not self._is_ignored((current_path / name).relative_to(root).as_posix())
            ]

            candidates = (
                [(current_path / name) for name in directories] if include_directories else []
            )
            candidates.extend(current_path / name for name in files)

            for path in candidates:
                if path.is_symlink():
                    continue

                relative = path.relative_to(root).as_posix()

                if self._is_ignored(relative):
                    continue

                visited += 1

                if visited > self._max_files:
                    logger.warning(
                        "Filesystem search stopped at max_files=%d",
                        self._max_files,
                    )
                    return

                yield path

    def _is_ignored(self, relative_path: str) -> bool:
        """Check whether a relative path matches configured ignore rules."""

        normalized = relative_path.replace("\\", "/")

        for pattern in self._ignore_patterns:
            pattern = pattern.replace("\\", "/")

            if fnmatch.fnmatchcase(normalized, pattern):
                return True

            if pattern.endswith("/**"):
                directory = pattern[:-3]
                if normalized == directory or normalized.startswith(directory + "/"):
                    return True

        return False

    def _validate_limit(self, value: int | None) -> int:
        limit = self._max_results if value is None else value

        if limit <= 0:
            raise ValueError("max_results must be positive.")

        return min(limit, self._max_results)

    @staticmethod
    def _validate_pattern(pattern: str) -> None:
        if not isinstance(pattern, str):
            raise TypeError("Search pattern must be a string.")

        if not pattern.strip():
            raise InvalidSearchPatternError("Search pattern cannot be empty.")

        if "\x00" in pattern:
            raise InvalidSearchPatternError("Search pattern cannot contain null bytes.")
