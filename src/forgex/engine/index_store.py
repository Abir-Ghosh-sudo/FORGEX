"""Persistent SQLite storage for the FORGEX repository index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from forgex.engine.indexing import IndexedFile, IndexedSymbol


class IndexStoreError(RuntimeError):
    """Raised when index storage operations fail."""


class IndexStore:
    """Persist repository indexing data in SQLite."""

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS indexed_files (
                        path TEXT PRIMARY KEY,
                        language TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        modified_time REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS indexed_symbols (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        line INTEGER NOT NULL,
                        signature TEXT NOT NULL,
                        FOREIGN KEY(file_path)
                            REFERENCES indexed_files(path)
                            ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_symbols_name
                        ON indexed_symbols(name);

                    CREATE INDEX IF NOT EXISTS idx_symbols_file
                        ON indexed_symbols(file_path);
                    """
                )
        except sqlite3.Error as exc:
            raise IndexStoreError(f"Unable to initialize index database: {exc}") from exc

    def save_file(self, item: IndexedFile) -> None:
        """Insert or replace a file and its symbols."""
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO indexed_files (
                        path, language, content_hash,
                        size_bytes, modified_time
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        language = excluded.language,
                        content_hash = excluded.content_hash,
                        size_bytes = excluded.size_bytes,
                        modified_time = excluded.modified_time
                    """,
                    (
                        item.path,
                        item.language,
                        item.content_hash,
                        item.size_bytes,
                        item.modified_time,
                    ),
                )

                connection.execute(
                    "DELETE FROM indexed_symbols WHERE file_path = ?",
                    (item.path,),
                )

                connection.executemany(
                    """
                    INSERT INTO indexed_symbols (
                        name, kind, file_path, line, signature
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            symbol.name,
                            symbol.kind,
                            symbol.file_path,
                            symbol.line,
                            symbol.signature,
                        )
                        for symbol in item.symbols
                    ],
                )
        except sqlite3.Error as exc:
            raise IndexStoreError(f"Unable to save indexed file: {exc}") from exc

    def save_many(self, files: tuple[IndexedFile, ...]) -> None:
        """Save multiple indexed files atomically."""
        try:
            with self._connect() as connection:
                for item in files:
                    connection.execute(
                        """
                        INSERT INTO indexed_files (
                            path, language, content_hash,
                            size_bytes, modified_time
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            language = excluded.language,
                            content_hash = excluded.content_hash,
                            size_bytes = excluded.size_bytes,
                            modified_time = excluded.modified_time
                        """,
                        (
                            item.path,
                            item.language,
                            item.content_hash,
                            item.size_bytes,
                            item.modified_time,
                        ),
                    )

                    connection.execute(
                        "DELETE FROM indexed_symbols WHERE file_path = ?",
                        (item.path,),
                    )

                    connection.executemany(
                        """
                        INSERT INTO indexed_symbols (
                            name, kind, file_path, line, signature
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                symbol.name,
                                symbol.kind,
                                symbol.file_path,
                                symbol.line,
                                symbol.signature,
                            )
                            for symbol in item.symbols
                        ],
                    )
        except sqlite3.Error as exc:
            raise IndexStoreError(f"Unable to save repository index: {exc}") from exc

    def load_all(self) -> tuple[IndexedFile, ...]:
        """Load all indexed files and their symbols."""
        try:
            with self._connect() as connection:
                rows = connection.execute("SELECT * FROM indexed_files ORDER BY path").fetchall()

                results = []

                for row in rows:
                    symbol_rows = connection.execute(
                        """
                        SELECT name, kind, file_path, line, signature
                        FROM indexed_symbols
                        WHERE file_path = ?
                        ORDER BY line
                        """,
                        (row["path"],),
                    ).fetchall()

                    symbols = tuple(
                        IndexedSymbol(
                            name=symbol["name"],
                            kind=symbol["kind"],
                            file_path=symbol["file_path"],
                            line=symbol["line"],
                            signature=symbol["signature"],
                        )
                        for symbol in symbol_rows
                    )

                    results.append(
                        IndexedFile(
                            path=row["path"],
                            language=row["language"],
                            content_hash=row["content_hash"],
                            size_bytes=row["size_bytes"],
                            modified_time=row["modified_time"],
                            symbols=symbols,
                        )
                    )

                return tuple(results)
        except sqlite3.Error as exc:
            raise IndexStoreError(f"Unable to load repository index: {exc}") from exc

    def search_symbols(
        self,
        query: str,
        limit: int = 100,
    ) -> tuple[IndexedSymbol, ...]:
        """Search indexed symbol names."""
        if not query.strip():
            return ()

        if limit <= 0:
            raise ValueError("limit must be positive.")

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT name, kind, file_path, line, signature
                    FROM indexed_symbols
                    WHERE name LIKE ? ESCAPE '\\'
                    ORDER BY name, file_path, line
                    LIMIT ?
                    """,
                    (
                        "%" + self._escape_like(query) + "%",
                        limit,
                    ),
                ).fetchall()

            return tuple(
                IndexedSymbol(
                    name=row["name"],
                    kind=row["kind"],
                    file_path=row["file_path"],
                    line=row["line"],
                    signature=row["signature"],
                )
                for row in rows
            )
        except sqlite3.Error as exc:
            raise IndexStoreError(f"Unable to search indexed symbols: {exc}") from exc

    def remove_file(self, path: str) -> bool:
        """Remove a file and its symbols."""
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM indexed_files WHERE path = ?",
                    (path,),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise IndexStoreError(f"Unable to remove indexed file: {exc}") from exc

    def clear(self) -> None:
        """Clear all indexed files and symbols."""
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM indexed_symbols")
                connection.execute("DELETE FROM indexed_files")
        except sqlite3.Error as exc:
            raise IndexStoreError(f"Unable to clear index: {exc}") from exc

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
