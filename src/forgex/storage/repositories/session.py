
"""SQLite-backed session repository for FORGEX."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from forgex.sessions.models import (
    CodingSession,
    MessageRole,
    SessionMessage,
    SessionStatus,
)

from ..database import Database


class SQLiteSessionRepository:
    """Persist coding sessions and messages in SQLite."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _serialize_datetime(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed

    @staticmethod
    def _serialize_json(value: dict[str, Any]) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _parse_json(value: str | None) -> dict[str, Any]:
        if not value:
            return {}

        result = json.loads(value)
        if not isinstance(result, dict):
            raise ValueError("Stored metadata must be a JSON object")

        return result

    def _row_to_message(self, row: Any) -> SessionMessage:
        return SessionMessage(
            id=row["id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            created_at=self._parse_datetime(row["created_at"]),
            token_count=row["token_count"],
            metadata=self._parse_json(row["metadata_json"]),
        )

    def _row_to_session(
        self,
        row: Any,
        *,
        include_messages: bool = False,
    ) -> CodingSession:
        session = CodingSession(
            id=row["id"],
            title=row["title"],
            workspace=row["workspace"],
            status=SessionStatus(row["status"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
            metadata=self._parse_json(row["metadata_json"]),
            total_tokens=row["total_tokens"],
        )

        if include_messages:
            messages = self.get_messages(session.id)
            session.messages = messages

        return session

    def create(self, session: CodingSession) -> CodingSession:
        """Insert a new session."""

        with self.database.transaction():
            self.database.execute(
                """
                INSERT INTO sessions (
                    id,
                    title,
                    workspace,
                    status,
                    created_at,
                    updated_at,
                    metadata_json,
                    total_tokens
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.title,
                    session.workspace,
                    session.status.value,
                    self._serialize_datetime(session.created_at),
                    self._serialize_datetime(session.updated_at),
                    self._serialize_json(session.metadata),
                    session.total_tokens,
                ),
            )

            for message in session.messages:
                self._insert_message(session.id, message)

        return self.get(session.id)

    def _insert_message(
        self,
        session_id: str,
        message: SessionMessage,
    ) -> None:
        self.database.execute(
            """
            INSERT INTO session_messages (
                id,
                session_id,
                role,
                content,
                created_at,
                token_count,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                session_id,
                message.role.value,
                message.content,
                self._serialize_datetime(message.created_at),
                message.token_count,
                self._serialize_json(message.metadata),
            ),
        )

    def get(self, session_id: str) -> CodingSession:
        """Retrieve a session and its messages."""

        row = self.database.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Session not found: {session_id}")

        return self._row_to_session(row, include_messages=True)

    def find(self, session_id: str) -> CodingSession | None:
        """Retrieve a session or return None."""

        row = self.database.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_session(row, include_messages=True)

    def list(
        self,
        *,
        workspace: str | None = None,
        status: SessionStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CodingSession]:
        """List sessions with optional filters."""

        if offset < 0:
            raise ValueError("offset cannot be negative")

        if limit is not None and limit < 0:
            raise ValueError("limit cannot be negative")

        conditions: list[str] = []
        parameters: list[Any] = []

        if workspace is not None:
            conditions.append("workspace = ?")
            parameters.append(workspace)

        if status is not None:
            conditions.append("status = ?")
            parameters.append(status.value)

        query = "SELECT * FROM sessions"

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY updated_at DESC"

        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        if offset:
            if limit is None:
                query += " LIMIT -1"
            query += " OFFSET ?"
            parameters.append(offset)

        rows = self.database.execute(
            query,
            tuple(parameters),
        ).fetchall()

        return [
            self._row_to_session(row, include_messages=False)
            for row in rows
        ]

    def update(self, session: CodingSession) -> CodingSession:
        """Update session metadata and lifecycle information."""

        with self.database.transaction():
            cursor = self.database.execute(
                """
                UPDATE sessions
                SET
                    title = ?,
                    workspace = ?,
                    status = ?,
                    updated_at = ?,
                    metadata_json = ?,
                    total_tokens = ?
                WHERE id = ?
                """,
                (
                    session.title,
                    session.workspace,
                    session.status.value,
                    self._serialize_datetime(session.updated_at),
                    self._serialize_json(session.metadata),
                    session.total_tokens,
                    session.id,
                ),
            )

            if cursor.rowcount == 0:
                raise KeyError(f"Session not found: {session.id}")

            self.database.execute(
                "DELETE FROM session_messages WHERE session_id = ?",
                (session.id,),
            )

            for message in session.messages:
                self._insert_message(session.id, message)

        return self.get(session.id)

    def delete(self, session_id: str) -> bool:
        """Delete a session and its associated messages."""

        cursor = self.database.execute(
            "DELETE FROM sessions WHERE id = ?",
            (session_id,),
        )
        return cursor.rowcount > 0

    def get_messages(
        self,
        session_id: str,
        *,
        limit: int | None = None,
    ) -> list[SessionMessage]:
        """Retrieve messages belonging to a session."""

        if limit is not None and limit < 0:
            raise ValueError("limit cannot be negative")

        query = """
            SELECT *
            FROM session_messages
            WHERE session_id = ?
            ORDER BY created_at ASC, rowid ASC
        """

        parameters: list[Any] = [session_id]

        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        rows = self.database.execute(
            query,
            tuple(parameters),
        ).fetchall()

        return [self._row_to_message(row) for row in rows]

    def add_message(
        self,
        session_id: str,
        message: SessionMessage,
    ) -> SessionMessage:
        """Persist a new message and update session counters."""

        with self.database.transaction():
            self._insert_message(session_id, message)

            cursor = self.database.execute(
                """
                UPDATE sessions
                SET
                    total_tokens = total_tokens + ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    message.token_count,
                    self._serialize_datetime(message.created_at),
                    session_id,
                ),
            )

            if cursor.rowcount == 0:
                raise KeyError(f"Session not found: {session_id}")

        return message

    def remove_message(
        self,
        session_id: str,
        message_id: str,
    ) -> bool:
        """Remove a message and recalculate the session token count."""

        with self.database.transaction():
            cursor = self.database.execute(
                """
                DELETE FROM session_messages
                WHERE id = ? AND session_id = ?
                """,
                (message_id, session_id),
            )

            if cursor.rowcount == 0:
                return False

            self.database.execute(
                """
                UPDATE sessions
                SET total_tokens = COALESCE(
                    (
                        SELECT SUM(token_count)
                        FROM session_messages
                        WHERE session_id = ?
                    ),
                    0
                )
                WHERE id = ?
                """,
                (session_id, session_id),
            )

        return True

    def clear_messages(self, session_id: str) -> int:
        """Remove all messages belonging to a session."""

        with self.database.transaction():
            cursor = self.database.execute(
                "DELETE FROM session_messages WHERE session_id = ?",
                (session_id,),
            )

            self.database.execute(
                "UPDATE sessions SET total_tokens = 0 WHERE id = ?",
                (session_id,),
            )

        return cursor.rowcount

    def count(self, *, workspace: str | None = None) -> int:
        """Return the number of stored sessions."""

        if workspace is None:
            row = self.database.execute(
                "SELECT COUNT(*) AS total FROM sessions"
            ).fetchone()
        else:
            row = self.database.execute(
                """
                SELECT COUNT(*) AS total
                FROM sessions
                WHERE workspace = ?
                """,
                (workspace,),
            ).fetchone()

        return int(row["total"])


__all__ = ["SQLiteSessionRepository"]
