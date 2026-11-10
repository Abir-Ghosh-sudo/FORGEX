
"""Tests for the SQLite-backed memory repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from forgex.storage.database import Database
from forgex.storage.repositories import SQLiteMemoryRepository
from forgex.storage.schemas import create_memory_schema


@pytest.fixture
def repository(tmp_path):
    """Create an isolated memory repository."""

    database = Database(tmp_path / "test_memory.db")
    database.initialize()
    create_memory_schema(database)

    yield SQLiteMemoryRepository(database)

    database.close_all()


def create_memory(
    repository,
    memory_id: str = "memory-1",
    *,
    workspace: str = "/project",
    content: str = "FORGEX is an AI coding agent.",
    category: str = "general",
    importance: float = 0.5,
):
    return repository.create(
        memory_id=memory_id,
        workspace=workspace,
        content=content,
        category=category,
        importance=importance,
    )


def test_create_and_get_memory(repository):
    created = create_memory(repository)

    retrieved = repository.get("memory-1")

    assert retrieved["id"] == created["id"]
    assert retrieved["content"] == created["content"]
    assert retrieved["workspace"] == "/project"


def test_find_missing_memory_returns_none(repository):
    assert repository.find("missing") is None


def test_get_missing_memory_raises(repository):
    with pytest.raises(KeyError):
        repository.get("missing")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"memory_id": ""},
        {"workspace": ""},
        {"content": ""},
        {"category": ""},
    ],
)
def test_create_rejects_empty_required_fields(repository, kwargs):
    arguments = {
        "memory_id": "memory-1",
        "workspace": "/project",
        "content": "Example memory",
        "category": "general",
        **kwargs,
    }

    with pytest.raises(ValueError):
        repository.create(**arguments)


@pytest.mark.parametrize("importance", [-0.1, 1.1])
def test_create_rejects_invalid_importance(repository, importance):
    with pytest.raises(ValueError):
        create_memory(repository, importance=importance)


def test_metadata_round_trip(repository):
    metadata = {
        "nested": {"enabled": True},
        "tags": ["python", "agent"],
    }

    repository.create(
        memory_id="memory-1",
        workspace="/project",
        content="Metadata test",
        metadata=metadata,
    )

    assert repository.get("memory-1")["metadata"] == metadata


def test_create_duplicate_memory_fails(repository):
    create_memory(repository)

    with pytest.raises(Exception):
        create_memory(repository)


def test_update_memory(repository):
    create_memory(repository)

    updated = repository.update(
        "memory-1",
        content="Updated FORGEX memory.",
        category="architecture",
        importance=0.9,
        metadata={"updated": True},
    )

    assert updated["content"] == "Updated FORGEX memory."
    assert updated["category"] == "architecture"
    assert updated["importance"] == 0.9
    assert updated["metadata"] == {"updated": True}


def test_update_preserves_unchanged_fields(repository):
    create_memory(repository)

    updated = repository.update(
        "memory-1",
        importance=0.8,
    )

    assert updated["content"] == "FORGEX is an AI coding agent."
    assert updated["category"] == "general"


def test_update_missing_memory_raises(repository):
    with pytest.raises(KeyError):
        repository.update("missing", content="Updated")


def test_update_rejects_empty_content(repository):
    create_memory(repository)

    with pytest.raises(ValueError):
        repository.update("memory-1", content="")


def test_update_rejects_invalid_importance(repository):
    create_memory(repository)

    with pytest.raises(ValueError):
        repository.update("memory-1", importance=1.5)


def test_content_hash_changes_after_update(repository):
    original = create_memory(repository)

    updated = repository.update(
        "memory-1",
        content="Completely different content.",
    )

    assert original["content_hash"] != updated["content_hash"]


def test_delete_memory(repository):
    create_memory(repository)

    assert repository.delete("memory-1") is True
    assert repository.find("memory-1") is None


def test_delete_missing_memory_returns_false(repository):
    assert repository.delete("missing") is False


def test_list_memories(repository):
    create_memory(repository, "memory-1")
    create_memory(repository, "memory-2")

    assert len(repository.list()) == 2


def test_list_filters_by_workspace(repository):
    create_memory(repository, "memory-1", workspace="/project")
    create_memory(repository, "memory-2", workspace="/another")

    results = repository.list(workspace="/project")

    assert len(results) == 1
    assert results[0]["id"] == "memory-1"


def test_list_filters_by_category(repository):
    create_memory(repository, "memory-1", category="general")
    create_memory(repository, "memory-2", category="architecture")

    results = repository.list(category="architecture")

    assert len(results) == 1
    assert results[0]["id"] == "memory-2"


def test_list_orders_by_importance(repository):
    create_memory(repository, "low", importance=0.2)
    create_memory(repository, "high", importance=0.9)
    create_memory(repository, "medium", importance=0.5)

    results = repository.list()

    assert [item["id"] for item in results] == [
        "high",
        "medium",
        "low",
    ]


def test_list_supports_pagination(repository):
    for index in range(5):
        create_memory(
            repository,
            f"memory-{index}",
            importance=0.5,
        )

    results = repository.list(limit=2, offset=1)

    assert len(results) == 2


def test_list_rejects_negative_limit(repository):
    with pytest.raises(ValueError):
        repository.list(limit=-1)


def test_list_rejects_negative_offset(repository):
    with pytest.raises(ValueError):
        repository.list(offset=-1)


def test_search_finds_matching_content(repository):
    create_memory(
        repository,
        "memory-1",
        content="FORGEX uses LangGraph for orchestration.",
    )
    create_memory(
        repository,
        "memory-2",
        content="Python supports asynchronous programming.",
    )

    results = repository.search("LangGraph")

    assert len(results) == 1
    assert results[0]["id"] == "memory-1"


def test_search_filters_by_workspace(repository):
    create_memory(
        repository,
        "memory-1",
        workspace="/project",
        content="Python coding agent",
    )
    create_memory(
        repository,
        "memory-2",
        workspace="/another",
        content="Python coding agent",
    )

    results = repository.search(
        "Python",
        workspace="/project",
    )

    assert len(results) == 1
    assert results[0]["id"] == "memory-1"


def test_search_filters_by_category(repository):
    create_memory(
        repository,
        "memory-1",
        content="LangGraph orchestration",
        category="architecture",
    )
    create_memory(
        repository,
        "memory-2",
        content="LangGraph debugging",
        category="debugging",
    )

    results = repository.search(
        "LangGraph",
        category="debugging",
    )

    assert len(results) == 1
    assert results[0]["id"] == "memory-2"


def test_search_empty_query_returns_empty_list(repository):
    create_memory(repository)

    assert repository.search("   ") == []


def test_search_rejects_negative_limit(repository):
    with pytest.raises(ValueError):
        repository.search("FORGEX", limit=-1)


def test_record_access_updates_statistics(repository):
    create_memory(repository)

    repository.record_access("memory-1")

    memory = repository.get("memory-1")

    assert memory["access_count"] == 1
    assert memory["last_accessed_at"] is not None


def test_record_access_missing_memory_raises(repository):
    with pytest.raises(KeyError):
        repository.record_access("missing")


def test_expired_memory_is_excluded_from_list(repository):
    expired = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()

    repository.create(
        memory_id="expired",
        workspace="/project",
        content="Expired memory",
        expires_at=expired,
    )

    assert repository.list() == []


def test_delete_expired_memory(repository):
    expired = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()

    repository.create(
        memory_id="expired",
        workspace="/project",
        content="Expired memory",
        expires_at=expired,
    )

    assert repository.delete_expired() == 1
    assert repository.find("expired") is None


def test_count_memories(repository):
    create_memory(repository, "memory-1", workspace="/project")
    create_memory(repository, "memory-2", workspace="/another")

    assert repository.count() == 2
    assert repository.count(workspace="/project") == 1


def test_add_and_get_chunk(repository):
    create_memory(repository)

    chunk = repository.add_chunk(
        chunk_id="chunk-1",
        memory_id="memory-1",
        chunk_index=0,
        content="FORGEX uses local coding models.",
        token_count=8,
    )

    restored = repository.get_chunk("chunk-1")

    assert restored["id"] == chunk["id"]
    assert restored["content"] == chunk["content"]
    assert restored["token_count"] == 8


def test_add_chunk_preserves_embedding_reference(repository):
    create_memory(repository)

    repository.add_chunk(
        chunk_id="chunk-1",
        memory_id="memory-1",
        chunk_index=0,
        content="Embedding test",
        embedding_ref="vector-store-id-123",
    )

    chunk = repository.get_chunk("chunk-1")

    assert chunk["embedding_ref"] == "vector-store-id-123"


def test_add_chunk_preserves_metadata(repository):
    create_memory(repository)

    metadata = {"source_page": 3, "section": "architecture"}

    repository.add_chunk(
        chunk_id="chunk-1",
        memory_id="memory-1",
        chunk_index=0,
        content="Chunk metadata test",
        metadata=metadata,
    )

    assert repository.get_chunk("chunk-1")["metadata"] == metadata


@pytest.mark.parametrize(
    "kwargs",
    [
        {"chunk_index": -1},
        {"token_count": -1},
        {"content": ""},
    ],
)
def test_add_chunk_rejects_invalid_values(repository, kwargs):
    create_memory(repository)

    arguments = {
        "chunk_id": "chunk-1",
        "memory_id": "memory-1",
        "chunk_index": 0,
        "content": "Valid chunk",
        "token_count": 0,
        **kwargs,
    }

    with pytest.raises(ValueError):
        repository.add_chunk(**arguments)


def test_add_chunk_for_missing_memory_fails(repository):
    with pytest.raises(Exception):
        repository.add_chunk(
            chunk_id="chunk-1",
            memory_id="missing",
            chunk_index=0,
            content="Orphan chunk",
        )


def test_get_missing_chunk_raises(repository):
    with pytest.raises(KeyError):
        repository.get_chunk("missing")


def test_get_chunks_returns_ordered_chunks(repository):
    create_memory(repository)

    repository.add_chunk(
        chunk_id="chunk-2",
        memory_id="memory-1",
        chunk_index=1,
        content="Second chunk",
    )
    repository.add_chunk(
        chunk_id="chunk-1",
        memory_id="memory-1",
        chunk_index=0,
        content="First chunk",
    )

    chunks = repository.get_chunks("memory-1")

    assert [chunk["chunk_index"] for chunk in chunks] == [0, 1]


def test_duplicate_chunk_index_is_rejected(repository):
    create_memory(repository)

    repository.add_chunk(
        chunk_id="chunk-1",
        memory_id="memory-1",
        chunk_index=0,
        content="First chunk",
    )

    with pytest.raises(Exception):
        repository.add_chunk(
            chunk_id="chunk-2",
            memory_id="memory-1",
            chunk_index=0,
            content="Duplicate index",
        )


def test_delete_chunk(repository):
    create_memory(repository)

    repository.add_chunk(
        chunk_id="chunk-1",
        memory_id="memory-1",
        chunk_index=0,
        content="Temporary chunk",
    )

    assert repository.delete_chunk("chunk-1") is True
    assert repository.get_chunks("memory-1") == []


def test_delete_memory_cascades_to_chunks(repository):
    create_memory(repository)

    repository.add_chunk(
        chunk_id="chunk-1",
        memory_id="memory-1",
        chunk_index=0,
        content="Child chunk",
    )

    repository.delete("memory-1")

    assert repository.get_chunks("memory-1") == []


def test_persistence_after_reopening_database(tmp_path):
    database_path = tmp_path / "persistent_memory.db"

    database = Database(database_path)
    database.initialize()
    create_memory_schema(database)

    repository = SQLiteMemoryRepository(database)

    repository.create(
        memory_id="memory-1",
        workspace="/project",
        content="Persistent FORGEX memory",
    )

    repository.add_chunk(
        chunk_id="chunk-1",
        memory_id="memory-1",
        chunk_index=0,
        content="Persistent RAG chunk",
    )

    database.close_all()

    reopened_database = Database(database_path)
    reopened_database.initialize()

    restored_repository = SQLiteMemoryRepository(reopened_database)

    memory = restored_repository.get("memory-1")
    chunks = restored_repository.get_chunks("memory-1")

    assert memory["content"] == "Persistent FORGEX memory"
    assert len(chunks) == 1
    assert chunks[0]["content"] == "Persistent RAG chunk"

    reopened_database.close_all()
