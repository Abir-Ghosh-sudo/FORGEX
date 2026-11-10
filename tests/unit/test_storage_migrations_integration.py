"""Integration tests for FORGEX storage migrations."""

import sqlite3

import pytest

from forgex.storage.migrations import get_migrations


@pytest.fixture
def connection():
    """Create an isolated in-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")

    yield conn

    conn.close()


def get_table_names(connection: sqlite3.Connection) -> set[str]:
    """Return all user-defined table names."""
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchall()

    return {row[0] for row in rows}


def test_migration_registry_has_sequential_versions():
    migrations = get_migrations()

    assert [migration.version for migration in migrations] == [1, 2]


def test_initial_migration_creates_session_tables(connection):
    initial = get_migrations()[0]

    initial.up(connection)

    tables = get_table_names(connection)

    assert "sessions" in tables
    assert "session_messages" in tables


def test_memory_migration_creates_memory_tables(connection):
    initial, memory = get_migrations()

    initial.up(connection)
    memory.up(connection)

    tables = get_table_names(connection)

    assert "sessions" in tables
    assert "session_messages" in tables
    assert "memory_entries" in tables
    assert "memory_chunks" in tables


def test_memory_migration_rollback_preserves_session_tables(connection):
    initial, memory = get_migrations()

    initial.up(connection)
    memory.up(connection)
    memory.down(connection)

    tables = get_table_names(connection)

    assert "sessions" in tables
    assert "session_messages" in tables
    assert "memory_entries" not in tables
    assert "memory_chunks" not in tables


def test_memory_tables_have_foreign_key_relationship(connection):
    initial, memory = get_migrations()

    initial.up(connection)
    memory.up(connection)

    foreign_keys = connection.execute(
        "PRAGMA foreign_key_list(memory_chunks)"
    ).fetchall()

    assert any(
        row[2] == "memory_entries" and row[6].upper() == "CASCADE"
        for row in foreign_keys
    )