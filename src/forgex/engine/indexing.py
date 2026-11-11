"""Repository indexing engine for FORGEX."""

from __future__ import annotations

import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from forgex.engine.parser import SourceParser

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IndexedSymbol:
    name: str
    kind: str
    file_path: str
    line: int
    signature: str = ""


@dataclass(frozen=True, slots=True)
class IndexedFile:
    path: str
    language: str
    content_hash: str
    size_bytes: int
    modified_time: float
    symbols: tuple[IndexedSymbol, ...] = ()


@dataclass(frozen=True, slots=True)
class IndexingResult:
    workspace: str
    indexed_files: int
    skipped_files: int
    failed_files: int
    symbols_found: int
    duration_seconds: float


class RepositoryIndexer:
    """Build and maintain a searchable repository index."""

    EXCLUDED_DIRECTORIES = {
        ".git", ".venv", "venv", "__pycache__",
        "node_modules", "dist", "build", ".tox",
        ".mypy_cache", ".pytest_cache", ".forgex",
    }

    def __init__(
        self,
        workspace: Path,
        parser: SourceParser | None = None,
        *,
        max_file_size: int = 5 * 1024 * 1024,
        workers: int | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

        if not self.workspace.is_dir():
            raise ValueError("Workspace must be an existing directory.")

        if max_file_size <= 0:
            raise ValueError("max_file_size must be positive.")

        self.parser = parser or SourceParser(max_file_size)
        self.max_file_size = max_file_size
        self.workers = workers or min(8, (os.cpu_count() or 2))

        self._index: dict[str, IndexedFile] = {}

    @property
    def index(self) -> dict[str, IndexedFile]:
        """Return a read-only copy of the current index."""
        return self._index.copy()

    def discover_files(self) -> tuple[Path, ...]:
        """Discover supported source files inside the workspace."""
        discovered: list[Path] = []

        for root, directories, filenames in os.walk(
            self.workspace,
            followlinks=False,
        ):
            directories[:] = sorted(
                directory
                for directory in directories
                if directory not in self.EXCLUDED_DIRECTORIES
                and not (Path(root) / directory).is_symlink()
            )

            for filename in filenames:
                path = Path(root) / filename

                if path.is_symlink():
                    continue

                if not self.parser.detect_language(path):
                    continue

                try:
                    if path.stat().st_size > self.max_file_size:
                        continue

                    path.resolve().relative_to(self.workspace)
                except (OSError, ValueError):
                    continue

                discovered.append(path)

        return tuple(sorted(discovered))

    def index_repository(
        self,
        *,
        incremental: bool = True,
    ) -> IndexingResult:
        """Index the repository, optionally skipping unchanged files."""
        import time

        started = time.monotonic()
        files = self.discover_files()

        indexed = 0
        skipped = 0
        failed = 0

        def process(path: Path) -> tuple[str, IndexedFile | None, bool]:
            relative = str(path.relative_to(self.workspace))

            try:
                stat = path.stat()
                content = path.read_bytes()
                content_hash = hashlib.sha256(content).hexdigest()

                previous = self._index.get(relative)

                if (
                    incremental
                    and previous is not None
                    and previous.content_hash == content_hash
                ):
                    return relative, previous, True

                language = self.parser.detect_language(path)

                if language is None:
                    return relative, None, False

                result = self.parser.parse_source(
                    content,
                    language,
                    file_path=relative,
                )

                symbols = tuple(
                    IndexedSymbol(
                        name=name,
                        kind=node.node_type,
                        file_path=relative,
                        line=node.start_line,
                        signature=node.text.splitlines()[0].strip(),
                    )
                    for node in self.parser.get_symbols(result)
                    if (name := self.parser._extract_symbol_name(node))
                )

                return (
                    relative,
                    IndexedFile(
                        path=relative,
                        language=language,
                        content_hash=content_hash,
                        size_bytes=stat.st_size,
                        modified_time=stat.st_mtime,
                        symbols=symbols,
                    ),
                    False,
                )

            except Exception:
                logger.exception("Failed to index %s", relative)
                return relative, None, False

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            results = executor.map(process, files)

            for relative, item, unchanged in results:
                if item is None:
                    failed += 1
                    continue

                self._index[relative] = item

                if unchanged:
                    skipped += 1
                else:
                    indexed += 1

        current_paths = {
            str(path.relative_to(self.workspace))
            for path in files
        }

        # Remove entries for deleted or no-longer-supported files.
        for relative in tuple(self._index):
            if relative not in current_paths:
                del self._index[relative]

        return IndexingResult(
            workspace=str(self.workspace),
            indexed_files=indexed,
            skipped_files=skipped,
            failed_files=failed,
            symbols_found=sum(
                len(item.symbols)
                for item in self._index.values()
            ),
            duration_seconds=time.monotonic() - started,
        )

    def get_file(self, path: str | Path) -> IndexedFile | None:
        """Get an indexed file by workspace-relative path."""
        candidate = Path(path)

        if candidate.is_absolute():
            try:
                candidate = candidate.resolve().relative_to(
                    self.workspace
                )
            except ValueError:
                return None

        return self._index.get(candidate.as_posix())

    def get_symbols(
        self,
        name: str | None = None,
    ) -> tuple[IndexedSymbol, ...]:
        """Return indexed symbols, optionally filtered by name."""
        symbols = (
            symbol
            for item in self._index.values()
            for symbol in item.symbols
        )

        if name is None:
            return tuple(symbols)

        needle = name.casefold()

        return tuple(
            symbol
            for symbol in symbols
            if needle in symbol.name.casefold()
        )

    def remove_file(self, path: str | Path) -> bool:
        """Remove a file from the index."""
        candidate = Path(path)

        if candidate.is_absolute():
            try:
                candidate = candidate.resolve().relative_to(
                    self.workspace
                )
            except ValueError:
                return False

        return self._index.pop(candidate.as_posix(), None) is not None

    def clear(self) -> None:
        """Clear the in-memory repository index."""
        self._index.clear()