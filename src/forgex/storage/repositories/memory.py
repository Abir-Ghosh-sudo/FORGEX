"""SQLite-backed persistent memory repository for FORGEX."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Final

_UNSET: Final = object()


class SQLiteMemoryRepository:
    """Persist long-term memory entries and RAG chunks."""

    def __init__(self, database: Any) -> None:
        self.database = database

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _serialize_metadata(metadata: dict[str, Any]) -> str:
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")

        try:
            return json.dumps(
                metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Metadata is not JSON serializable: {exc}") from exc

    @staticmethod
    def _parse_metadata(value: str | None) -> dict[str, Any]:
        if not value:
            return {}

        try:
            result = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid memory metadata JSON") from exc

        if not isinstance(result, dict):
            raise ValueError("Memory metadata must be a JSON object")

        return result

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_importance(importance: float) -> None:
        if isinstance(importance, bool) or not isinstance(importance, (int, float)):
            raise ValueError("importance must be a number")

        if not 0.0 <= importance <= 1.0:
            raise ValueError("importance must be between 0.0 and 1.0")

    @staticmethod
    def _validate_text(value: str, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} cannot be empty")

    @staticmethod
    def _escape_like(value: str) -> str:
        """Escape SQL LIKE wildcard characters."""
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _row_to_entry(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "workspace": row["workspace"],
            "category": row["category"],
            "content": row["content"],
            "source": row["source"],
            "source_id": row["source_id"],
            "content_hash": row["content_hash"],
            "importance": row["importance"],
            "access_count": row["access_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_accessed_at": row["last_accessed_at"],
            "expires_at": row["expires_at"],
            "metadata": self._parse_metadata(row["metadata_json"]),
        }

    def create(
        self,
        *,
        memory_id: str,
        workspace: str,
        content: str,
        category: str = "general",
        source: str | None = None,
        source_id: str | None = None,
        importance: float = 0.5,
        expires_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a persistent memory entry."""

        self._validate_text(memory_id, "memory_id")
        self._validate_text(workspace, "workspace")
        self._validate_text(content, "content")
        self._validate_text(category, "category")
        self._validate_importance(importance)

        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")

        now = self._now()

        self.database.execute(
            """
            INSERT INTO memory_entries (
                id,
                workspace,
                category,
                content,
                source,
                source_id,
                content_hash,
                importance,
                access_count,
                created_at,
                updated_at,
                expires_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                memory_id,
                workspace,
                category,
                content,
                source,
                source_id,
                self._content_hash(content),
                importance,
                now,
                now,
                expires_at,
                self._serialize_metadata(metadata or {}),
            ),
        )

        return self.get(memory_id)

    def get(self, memory_id: str) -> dict[str, Any]:
        """Retrieve a memory entry by ID."""

        row = self.database.execute(
            """
            SELECT *
            FROM memory_entries
            WHERE id = ?
            """,
            (memory_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Memory entry not found: {memory_id}")

        return self._row_to_entry(row)

    def find(self, memory_id: str) -> dict[str, Any] | None:
        """Find a memory entry without raising when absent."""

        row = self.database.execute(
            """
            SELECT *
            FROM memory_entries
            WHERE id = ?
            """,
            (memory_id,),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_entry(row)

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        category: str | None = None,
        importance: float | None = None,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        """Update selected memory fields.

        Pass expires_at=None explicitly to remove an existing expiry.
        Omit expires_at to preserve the current expiry.
        """

        current = self.get(memory_id)

        new_content = current["content"] if content is None else content
        new_category = current["category"] if category is None else category
        new_importance = current["importance"] if importance is None else importance
        new_metadata = current["metadata"] if metadata is None else metadata
        new_expiry = current["expires_at"] if expires_at is _UNSET else expires_at

        self._validate_text(new_content, "content")
        self._validate_text(new_category, "category")
        self._validate_importance(new_importance)

        if not isinstance(new_metadata, dict):
            raise ValueError("metadata must be a dictionary")

        if new_expiry is not None and not isinstance(new_expiry, str):
            raise ValueError("expires_at must be a string or None")

        self.database.execute(
            """
            UPDATE memory_entries
            SET
                content = ?,
                category = ?,
                importance = ?,
                content_hash = ?,
                metadata_json = ?,
                expires_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                new_content,
                new_category,
                new_importance,
                self._content_hash(new_content),
                self._serialize_metadata(new_metadata),
                new_expiry,
                self._now(),
                memory_id,
            ),
        )

        return self.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        """Delete a memory and its associated chunks."""

        cursor = self.database.execute(
            """
            DELETE FROM memory_entries
            WHERE id = ?
            """,
            (memory_id,),
        )

        return cursor.rowcount > 0

    def list(
        self,
        *,
        workspace: str | None = None,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List non-expired memories with optional filters."""

        if limit < 0 or offset < 0:
            raise ValueError("limit and offset cannot be negative")

        conditions = ["(expires_at IS NULL OR expires_at > ?)"]
        parameters: list[Any] = [self._now()]

        if workspace is not None:
            conditions.append("workspace = ?")
            parameters.append(workspace)

        if category is not None:
            conditions.append("category = ?")
            parameters.append(category)

        query = f"""
            SELECT *
            FROM memory_entries
            WHERE {" AND ".join(conditions)}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ? OFFSET ?
        """

        parameters.extend([limit, offset])

        rows = self.database.execute(
            query,
            tuple(parameters),
        ).fetchall()

        return [self._row_to_entry(row) for row in rows]

    def search(
        self,
        query: str,
        *,
        workspace: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Perform a basic SQLite lexical search.

        Semantic retrieval is delegated to the vector-store integration.
        SQL LIKE wildcard characters in the query are treated literally.
        """

        if not isinstance(query, str):
            raise ValueError("query must be a string")

        if not query.strip():
            return []

        if limit < 0:
            raise ValueError("limit cannot be negative")

        escaped_query = self._escape_like(query.strip())

        conditions = [
            "content LIKE ? ESCAPE '\\'",
            "(expires_at IS NULL OR expires_at > ?)",
        ]

        parameters: list[Any] = [
            f"%{escaped_query}%",
            self._now(),
        ]

        if workspace is not None:
            conditions.append("workspace = ?")
            parameters.append(workspace)

        if category is not None:
            conditions.append("category = ?")
            parameters.append(category)

        sql = f"""
            SELECT *
            FROM memory_entries
            WHERE {" AND ".join(conditions)}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
        """

        parameters.append(limit)

        rows = self.database.execute(
            sql,
            tuple(parameters),
        ).fetchall()

        return [self._row_to_entry(row) for row in rows]

    def record_access(self, memory_id: str) -> None:
        """Update memory access statistics."""

        cursor = self.database.execute(
            """
            UPDATE memory_entries
            SET
                access_count = access_count + 1,
                last_accessed_at = ?
            WHERE id = ?
            """,
            (self._now(), memory_id),
        )

        if cursor.rowcount == 0:
            raise KeyError(f"Memory entry not found: {memory_id}")

    def add_chunk(
        self,
        *,
        chunk_id: str,
        memory_id: str,
        chunk_index: int,
        content: str,
        token_count: int = 0,
        embedding_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a searchable chunk to an existing memory."""

        self._validate_text(chunk_id, "chunk_id")
        self._validate_text(memory_id, "memory_id")
        self._validate_text(content, "content")

        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
            raise ValueError("chunk_index must be a non-negative integer")

        if isinstance(token_count, bool) or not isinstance(token_count, int) or token_count < 0:
            raise ValueError("token_count must be a non-negative integer")

        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")

        now = self._now()

        self.database.execute(
            """
            INSERT INTO memory_chunks (
                id,
                memory_id,
                chunk_index,
                content,
                token_count,
                embedding_ref,
                content_hash,
                created_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                memory_id,
                chunk_index,
                content,
                token_count,
                embedding_ref,
                self._content_hash(content),
                now,
                self._serialize_metadata(metadata or {}),
            ),
        )

        return self.get_chunk(chunk_id)

    def get_chunk(self, chunk_id: str) -> dict[str, Any]:
        """Retrieve a memory chunk."""

        row = self.database.execute(
            """
            SELECT *
            FROM memory_chunks
            WHERE id = ?
            """,
            (chunk_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Memory chunk not found: {chunk_id}")

        return {
            "id": row["id"],
            "memory_id": row["memory_id"],
            "chunk_index": row["chunk_index"],
            "content": row["content"],
            "token_count": row["token_count"],
            "embedding_ref": row["embedding_ref"],
            "content_hash": row["content_hash"],
            "created_at": row["created_at"],
            "metadata": self._parse_metadata(row["metadata_json"]),
        }

    def get_chunks(
        self,
        memory_id: str,
    ) -> list[dict[str, Any]]:
        """Retrieve all chunks belonging to a memory."""

        rows = self.database.execute(
            """
            SELECT id
            FROM memory_chunks
            WHERE memory_id = ?
            ORDER BY chunk_index ASC
            """,
            (memory_id,),
        ).fetchall()

        return [self.get_chunk(row["id"]) for row in rows]

    def delete_chunk(self, chunk_id: str) -> bool:
        """Delete one memory chunk."""

        cursor = self.database.execute(
            """
            DELETE FROM memory_chunks
            WHERE id = ?
            """,
            (chunk_id,),
        )

        return cursor.rowcount > 0

    def count(
        self,
        *,
        workspace: str | None = None,
    ) -> int:
        """Count non-expired memory entries."""

        query = """
            SELECT COUNT(*) AS total
            FROM memory_entries
            WHERE (expires_at IS NULL OR expires_at > ?)
        """

        parameters: list[Any] = [self._now()]

        if workspace is not None:
            query += " AND workspace = ?"
            parameters.append(workspace)

        row = self.database.execute(
            query,
            tuple(parameters),
        ).fetchone()

        return int(row["total"])

    def delete_expired(self) -> int:
        """Delete expired memory entries and their chunks."""

        cursor = self.database.execute(
            """
            DELETE FROM memory_entries
            WHERE expires_at IS NOT NULL
              AND expires_at <= ?
            """,
            (self._now(),),
        )

        return cursor.rowcount


__all__ = ["SQLiteMemoryRepository"]
