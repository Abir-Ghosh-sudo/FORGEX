"""Database migration for persistent memory storage."""

import sqlite3

from forgex.storage.schemas.memory import (
    CREATE_MEMORY_CHUNKS_TABLE,
    CREATE_MEMORY_ENTRIES_TABLE,
    CREATE_MEMORY_INDEXES,
)

from .manager import Migration


def upgrade(connection: sqlite3.Connection) -> None:
    """Create persistent memory tables and indexes."""
    connection.execute(CREATE_MEMORY_ENTRIES_TABLE)
    connection.execute(CREATE_MEMORY_CHUNKS_TABLE)

    for statement in CREATE_MEMORY_INDEXES:
        connection.execute(statement)


def downgrade(connection: sqlite3.Connection) -> None:
    """Remove persistent memory tables."""
    connection.execute("DROP TABLE IF EXISTS memory_chunks")
    connection.execute("DROP TABLE IF EXISTS memory_entries")


def build_memory_migration() -> Migration:
    """Build the version 2 memory schema migration."""
    return Migration(
        version=2,
        name="memory_schema",
        up=upgrade,
        down=downgrade,
    )


__all__ = [
    "upgrade",
    "downgrade",
    "build_memory_migration",
]