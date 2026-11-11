"""Initial database schema migration for FORGEX."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .manager import Migration

if TYPE_CHECKING:
    from ..database import Database


def upgrade(database: Database) -> None:
    """Create the initial FORGEX database schema."""

    database.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            workspace TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            total_tokens INTEGER NOT NULL DEFAULT 0
                CHECK (total_tokens >= 0)
        )
        """
    )

    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sessions_workspace
        ON sessions(workspace)
        """
    )

    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sessions_status
        ON sessions(status)
        """
    )

    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
        ON sessions(updated_at DESC)
        """
    )

    database.execute(
        """
        CREATE TABLE IF NOT EXISTS session_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0
                CHECK (token_count >= 0),
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (session_id)
                REFERENCES sessions(id)
                ON DELETE CASCADE
        )
        """
    )

    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_session_messages_session
        ON session_messages(session_id, created_at)
        """
    )


def downgrade(database: Database) -> None:
    """Remove the initial FORGEX database schema."""

    database.execute("DROP TABLE IF EXISTS session_messages")
    database.execute("DROP TABLE IF EXISTS sessions")


def build_initial_migration() -> Migration:
    """Build the initial schema migration."""

    return Migration(
        version=1,
        name="initial_schema",
        up=upgrade,
        down=downgrade,
    )


__all__ = [
    "build_initial_migration",
    "upgrade",
    "downgrade",
]
