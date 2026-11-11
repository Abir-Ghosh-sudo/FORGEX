"""Repository index lifecycle manager for FORGEX."""

from __future__ import annotations

import threading
from pathlib import Path

from forgex.engine.indexing import (
    IndexedFile,
    IndexedSymbol,
    IndexingResult,
    RepositoryIndexer,
)
from forgex.engine.index_store import IndexStore


class IndexManagerError(RuntimeError):
    """Raised when index management fails."""


class IndexManager:
    """Manage repository indexing and persistent storage."""

    def __init__(
        self,
        workspace: Path,
        database_path: Path,
        *,
        indexer: RepositoryIndexer | None = None,
        store: IndexStore | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

        if not self.workspace.is_dir():
            raise IndexManagerError(
                f"Workspace does not exist: {self.workspace}"
            )

        self.indexer = indexer or RepositoryIndexer(self.workspace)
        self.store = store or IndexStore(database_path)
        self._lock = threading.RLock()

        self._validate_components()
        self._load_existing_index()

    def _validate_components(self) -> None:
        if self.indexer.workspace != self.workspace:
            raise IndexManagerError(
                "Indexer workspace does not match manager workspace."
            )

    def _load_existing_index(self) -> None:
        """Restore persisted index into memory."""
        with self._lock:
            try:
                for item in self.store.load_all():
                    self.indexer._index[item.path] = item
            except Exception as exc:
                raise IndexManagerError(
                    f"Unable to restore repository index: {exc}"
                ) from exc

    @property
    def files(self) -> tuple[IndexedFile, ...]:
        with self._lock:
            return tuple(self.indexer.index.values())

    @property
    def symbols(self) -> tuple[IndexedSymbol, ...]:
        with self._lock:
            return self.indexer.get_symbols()

    def build(
        self,
        *,
        incremental: bool = True,
    ) -> IndexingResult:
        """Build or update the repository index."""
        with self._lock:
            try:
                result = self.indexer.index_repository(
                    incremental=incremental
                )

                self.store.save_many(self.files)

                # Remove persisted records for files no longer present.
                indexed_paths = {
                    item.path for item in self.files
                }

                persisted_paths = {
                    item.path for item in self.store.load_all()
                }

                for removed_path in persisted_paths - indexed_paths:
                    self.store.remove_file(removed_path)

                return result

            except Exception as exc:
                raise IndexManagerError(
                    f"Repository indexing failed: {exc}"
                ) from exc

    def get_file(
        self,
        path: str | Path,
    ) -> IndexedFile | None:
        with self._lock:
            return self.indexer.get_file(path)

    def search_symbols(
        self,
        query: str,
        *,
        limit: int = 100,
    ) -> tuple[IndexedSymbol, ...]:
        if not query.strip():
            return ()

        with self._lock:
            return self.store.search_symbols(
                query,
                limit=limit,
            )

    def get_file_symbols(
        self,
        path: str | Path,
    ) -> tuple[IndexedSymbol, ...]:
        with self._lock:
            item = self.indexer.get_file(path)

            return item.symbols if item else ()

    def remove_file(self, path: str | Path) -> bool:
        """Remove a file from both in-memory and persistent indexes."""
        with self._lock:
            candidate = Path(path)

            if candidate.is_absolute():
                try:
                    candidate = candidate.resolve().relative_to(
                        self.workspace
                    )
                except ValueError:
                    return False

            relative = candidate.as_posix()

            removed_memory = self.indexer.remove_file(relative)
            removed_storage = self.store.remove_file(relative)

            return removed_memory or removed_storage

    def clear(self) -> None:
        """Clear both in-memory and persistent indexes."""
        with self._lock:
            self.indexer.clear()
            self.store.clear()

    def refresh(self) -> IndexingResult:
        """Perform an incremental repository refresh."""
        return self.build(incremental=True)