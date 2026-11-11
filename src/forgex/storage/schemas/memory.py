"""SQLite schema definitions for FORGEX persistent memory."""

from __future__ import annotations

CREATE_MEMORY_ENTRIES_TABLE = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id TEXT PRIMARY KEY,
    workspace TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    content TEXT NOT NULL,
    source TEXT,
    source_id TEXT,
    content_hash TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5
        CHECK (importance >= 0.0 AND importance <= 1.0),
    access_count INTEGER NOT NULL DEFAULT 0
        CHECK (access_count >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT,
    expires_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
)
"""


CREATE_MEMORY_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS memory_chunks (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL
        CHECK (chunk_index >= 0),
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0
        CHECK (token_count >= 0),
    embedding_ref TEXT,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(memory_id, chunk_index),
    FOREIGN KEY (memory_id)
        REFERENCES memory_entries(id)
        ON DELETE CASCADE
)
"""


CREATE_MEMORY_INDEXES = (
    """
    CREATE INDEX IF NOT EXISTS idx_memory_workspace
    ON memory_entries(workspace)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_category
    ON memory_entries(category)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_importance
    ON memory_entries(importance DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_updated_at
    ON memory_entries(updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_expires_at
    ON memory_entries(expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_content_hash
    ON memory_entries(content_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memory_chunks_memory
    ON memory_chunks(memory_id, chunk_index)
    """,
)


def create_memory_schema(database: object) -> None:
    """Create persistent memory tables and indexes."""

    execute = getattr(database, "execute", None)
    if not callable(execute):
        raise TypeError("database must provide a callable execute() method")

    execute(CREATE_MEMORY_ENTRIES_TABLE)
    execute(CREATE_MEMORY_CHUNKS_TABLE)

    for statement in CREATE_MEMORY_INDEXES:
        execute(statement)


__all__ = [
    "CREATE_MEMORY_ENTRIES_TABLE",
    "CREATE_MEMORY_CHUNKS_TABLE",
    "CREATE_MEMORY_INDEXES",
    "create_memory_schema",
]
