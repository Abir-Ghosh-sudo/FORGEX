"""SQLite-backed persistent memory store for FORGEX."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from forgex.memory.memory_store import (
    MemoryItem,
    MemorySearchResult,
    MemoryStore,
)

logger = logging.getLogger(__name__)


class SQLiteMemoryStore(MemoryStore):
    """Persistent memory store using SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.database_path))
            self._conn.row_factory = sqlite3.Row
            self._init_db()
        return self._conn

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.database_path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    embedding TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_items(memory_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at ON memory_items(created_at)"
            )
            conn.commit()
        finally:
            conn.close()

    async def add(self, item: MemoryItem) -> str:
        """Add a memory item."""
        item_id = item.id or str(uuid.uuid4())
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_items
                (id, content, memory_type, metadata, created_at, updated_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    item.content,
                    item.memory_type,
                    json.dumps(item.metadata),
                    item.created_at or time.time(),
                    item.updated_at or time.time(),
                    json.dumps(item.embedding) if item.embedding is not None else None,
                ),
            )
            conn.commit()
            return item_id
        except Exception:
            logger.exception("Failed to add memory item.")
            raise

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        """Search memory items by keyword (simple text match)."""
        conn = self._get_conn()
        try:
            like = f"%{query}%"
            cursor = conn.execute(
                """
                SELECT id, content, memory_type, metadata, created_at, updated_at, embedding
                FROM memory_items
                WHERE content LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (like, limit),
            )
            results: list[MemorySearchResult] = []
            for row in cursor.fetchall():
                item = self._row_to_item(row)
                score = 1.0 if query.lower() in item.content.lower() else 0.5
                results.append(MemorySearchResult(item=item, score=score))
            return results
        except Exception:
            logger.exception("Memory search failed.")
            raise

    async def get(self, memory_id: str) -> MemoryItem | None:
        """Get a memory item by ID."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """
                SELECT id, content, memory_type, metadata, created_at, updated_at, embedding
                FROM memory_items WHERE id = ?
                """,
                (memory_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_item(row)
        except Exception:
            logger.exception("Failed to get memory item.")
            raise

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory item by ID."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM memory_items WHERE id = ?",
                (memory_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            logger.exception("Failed to delete memory item.")
            raise

    async def clear(self) -> bool:
        """Clear all memory items."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM memory_items")
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to clear memory.")
            raise

    def _row_to_item(self, row: sqlite3.Row) -> MemoryItem:
        embedding = None
        if row["embedding"]:
            try:
                embedding = json.loads(row["embedding"])
            except Exception:
                embedding = None
        return MemoryItem(
            id=row["id"],
            content=row["content"],
            memory_type=row["memory_type"],
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            embedding=embedding,
        )

    async def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                logger.debug("Memory store close error.", exc_info=True)
            self._conn = None


__all__ = ["SQLiteMemoryStore"]
