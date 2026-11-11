"""SQLite schema definitions for FORGEX sessions and messages."""

from __future__ import annotations

CREATE_SESSIONS_TABLE = """
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


CREATE_SESSION_MESSAGES_TABLE = """
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


CREATE_SESSION_INDEXES = (
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_workspace
    ON sessions(workspace)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_status
    ON sessions(status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
    ON sessions(updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_session_messages_session
    ON session_messages(session_id, created_at)
    """,
)


def create_session_schema(database: object) -> None:
    """Create session tables and indexes on a database connection."""

    execute = getattr(database, "execute", None)
    if not callable(execute):
        raise TypeError("database must provide a callable execute() method")

    execute(CREATE_SESSIONS_TABLE)
    execute(CREATE_SESSION_MESSAGES_TABLE)

    for statement in CREATE_SESSION_INDEXES:
        execute(statement)


__all__ = [
    "CREATE_SESSIONS_TABLE",
    "CREATE_SESSION_MESSAGES_TABLE",
    "CREATE_SESSION_INDEXES",
    "create_session_schema",
]
