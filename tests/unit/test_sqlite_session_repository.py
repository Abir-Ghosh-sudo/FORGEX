
"""Tests for the SQLite-backed session repository."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from forgex.sessions.models import (
    CodingSession,
    MessageRole,
    SessionMessage,
    SessionStatus,
)
from forgex.storage.database import Database
from forgex.storage.repositories import SQLiteSessionRepository
from forgex.storage.schemas import create_session_schema


@pytest.fixture
def repository(tmp_path):
    """Create an isolated SQLite repository."""

    database = Database(tmp_path / "test_sessions.db")
    database.initialize()
    create_session_schema(database)

    repo = SQLiteSessionRepository(database)

    yield repo

    database.close_all()


def make_session(
    session_id: str = "session-1",
    *,
    workspace: str = "/project",
    title: str = "Test session",
) -> CodingSession:
    now = datetime.now(timezone.utc)

    return CodingSession(
        id=session_id,
        title=title,
        workspace=workspace,
        status=SessionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        metadata={"source": "test"},
        total_tokens=0,
    )


def make_message(
    message_id: str = "message-1",
    *,
    role: MessageRole = MessageRole.USER,
    content: str = "Hello FORGEX",
    token_count: int = 5,
) -> SessionMessage:
    return SessionMessage(
        id=message_id,
        role=role,
        content=content,
        created_at=datetime.now(timezone.utc),
        token_count=token_count,
        metadata={"test": True},
    )


def test_create_and_get_session(repository):
    session = make_session()

    created = repository.create(session)
    retrieved = repository.get(session.id)

    assert created.id == session.id
    assert retrieved.title == session.title
    assert retrieved.workspace == session.workspace
    assert retrieved.metadata == session.metadata
    assert retrieved.status == SessionStatus.ACTIVE


def test_find_missing_session_returns_none(repository):
    assert repository.find("missing") is None


def test_get_missing_session_raises(repository):
    with pytest.raises(KeyError):
        repository.get("missing")


def test_create_session_with_messages(repository):
    session = make_session()
    message = make_message()

    session.messages.append(message)
    session.total_tokens = message.token_count

    repository.create(session)

    retrieved = repository.get(session.id)

    assert len(retrieved.messages) == 1
    assert retrieved.messages[0].content == message.content
    assert retrieved.total_tokens == 5


def test_session_metadata_round_trip(repository):
    session = make_session()
    session.metadata = {
        "nested": {"enabled": True},
        "tags": ["python", "ai"],
    }

    repository.create(session)

    retrieved = repository.get(session.id)

    assert retrieved.metadata == session.metadata


def test_create_duplicate_session_fails(repository):
    repository.create(make_session())

    with pytest.raises(Exception):
        repository.create(make_session())


def test_list_sessions(repository):
    repository.create(make_session("session-1"))
    repository.create(make_session("session-2"))
    repository.create(
        make_session("session-3", workspace="/another-project")
    )

    sessions = repository.list()

    assert len(sessions) == 3


def test_list_filters_by_workspace(repository):
    repository.create(make_session("session-1"))
    repository.create(
        make_session("session-2", workspace="/another-project")
    )

    sessions = repository.list(workspace="/project")

    assert len(sessions) == 1
    assert sessions[0].id == "session-1"


def test_list_filters_by_status(repository):
    active = make_session("active")
    completed = make_session("completed")
    completed.status = SessionStatus.COMPLETED

    repository.create(active)
    repository.create(completed)

    sessions = repository.list(status=SessionStatus.COMPLETED)

    assert len(sessions) == 1
    assert sessions[0].id == "completed"


def test_list_supports_pagination(repository):
    for index in range(5):
        repository.create(make_session(f"session-{index}"))

    sessions = repository.list(limit=2, offset=1)

    assert len(sessions) == 2


def test_list_rejects_negative_offset(repository):
    with pytest.raises(ValueError):
        repository.list(offset=-1)


def test_list_rejects_negative_limit(repository):
    with pytest.raises(ValueError):
        repository.list(limit=-1)


def test_update_session(repository):
    session = make_session()
    repository.create(session)

    session.title = "Updated session"
    session.metadata["updated"] = True

    updated = repository.update(session)

    assert updated.title == "Updated session"
    assert updated.metadata["updated"] is True


def test_update_missing_session_raises(repository):
    with pytest.raises(KeyError):
        repository.update(make_session("missing"))


def test_delete_session(repository):
    repository.create(make_session())

    assert repository.delete("session-1") is True
    assert repository.find("session-1") is None


def test_delete_missing_session_returns_false(repository):
    assert repository.delete("missing") is False


def test_add_and_get_message(repository):
    repository.create(make_session())

    message = make_message()
    repository.add_message("session-1", message)

    messages = repository.get_messages("session-1")

    assert len(messages) == 1
    assert messages[0].id == message.id
    assert messages[0].role == MessageRole.USER


def test_add_message_updates_token_count(repository):
    repository.create(make_session())

    repository.add_message(
        "session-1",
        make_message(token_count=12),
    )

    session = repository.get("session-1")

    assert session.total_tokens == 12


def test_add_message_to_missing_session_fails(repository):
    with pytest.raises(Exception):
        repository.add_message(
            "missing",
            make_message(),
        )


def test_remove_message(repository):
    repository.create(make_session())
    repository.add_message("session-1", make_message())

    removed = repository.remove_message(
        "session-1",
        "message-1",
    )

    assert removed is True
    assert repository.get_messages("session-1") == []


def test_remove_message_recalculates_tokens(repository):
    repository.create(make_session())

    repository.add_message(
        "session-1",
        make_message("message-1", token_count=10),
    )
    repository.add_message(
        "session-1",
        make_message("message-2", token_count=20),
    )

    repository.remove_message("session-1", "message-1")

    assert repository.get("session-1").total_tokens == 20


def test_remove_missing_message_returns_false(repository):
    repository.create(make_session())

    assert repository.remove_message(
        "session-1",
        "missing",
    ) is False


def test_clear_messages(repository):
    repository.create(make_session())

    repository.add_message(
        "session-1",
        make_message("message-1"),
    )
    repository.add_message(
        "session-1",
        make_message("message-2"),
    )

    removed = repository.clear_messages("session-1")

    assert removed == 2
    assert repository.get_messages("session-1") == []
    assert repository.get("session-1").total_tokens == 0


def test_get_messages_supports_limit(repository):
    repository.create(make_session())

    for index in range(4):
        repository.add_message(
            "session-1",
            make_message(f"message-{index}"),
        )

    messages = repository.get_messages("session-1", limit=2)

    assert len(messages) == 2


def test_get_messages_rejects_negative_limit(repository):
    with pytest.raises(ValueError):
        repository.get_messages("session-1", limit=-1)


def test_count_sessions(repository):
    repository.create(make_session("session-1"))
    repository.create(
        make_session("session-2", workspace="/another-project")
    )

    assert repository.count() == 2
    assert repository.count(workspace="/project") == 1


def test_delete_cascades_to_messages(repository):
    repository.create(make_session())
    repository.add_message("session-1", make_message())

    repository.delete("session-1")

    assert repository.get_messages("session-1") == []


def test_persistence_after_reopening_database(tmp_path):
    database_path = tmp_path / "persistent.db"

    database = Database(database_path)
    database.initialize()
    create_session_schema(database)

    repository = SQLiteSessionRepository(database)
    repository.create(make_session())
    repository.add_message("session-1", make_message())

    database.close_all()

    reopened_database = Database(database_path)
    reopened_database.initialize()

    reopened_repository = SQLiteSessionRepository(reopened_database)
    restored = reopened_repository.get("session-1")

    assert restored.id == "session-1"
    assert len(restored.messages) == 1
    assert restored.messages[0].content == "Hello FORGEX"

    reopened_database.close_all()


def test_message_metadata_round_trip(repository):
    repository.create(make_session())

    message = make_message()
    message.metadata = {
        "nested": {"important": True},
        "tags": ["debug", "test"],
    }

    repository.add_message("session-1", message)

    restored = repository.get_messages("session-1")[0]

    assert restored.metadata == message.metadata


def test_message_content_round_trip(repository):
    repository.create(make_session())

    content = "Unicode test: বাংলা, 日本語, 🚀"
    repository.add_message(
        "session-1",
        make_message(content=content),
    )

    restored = repository.get_messages("session-1")[0]

    assert restored.content == content


def test_create_and_retrieve_preserves_timestamps(repository):
    session = make_session()
    repository.create(session)

    restored = repository.get(session.id)

    assert restored.created_at == session.created_at
    assert restored.updated_at == session.updated_at


def test_update_replaces_messages(repository):
    session = make_session()
    session.messages.append(make_message("old-message"))
    session.total_tokens = 5

    repository.create(session)

    session.messages = [make_message("new-message", token_count=8)]
    session.total_tokens = 8

    repository.update(session)

    messages = repository.get_messages(session.id)

    assert len(messages) == 1
    assert messages[0].id == "new-message"
    assert repository.get(session.id).total_tokens == 8
