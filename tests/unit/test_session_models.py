
"""Unit tests for FORGEX session domain models."""

from datetime import timedelta
from uuid import UUID

import pytest

from forgex.sessions.models import (
    CodingSession,
    MessageRole,
    SessionMessage,
    SessionStatus,
    utc_now,
)


@pytest.fixture
def session() -> CodingSession:
    return CodingSession(
        workspace="C:/projects/demo",
        title="Test Session",
    )


def test_create_session(session: CodingSession) -> None:
    assert isinstance(session.id, UUID)
    assert session.workspace == "C:/projects/demo"
    assert session.title == "Test Session"
    assert session.status == SessionStatus.ACTIVE
    assert session.messages == []
    assert session.total_tokens == 0


def test_create_message() -> None:
    message = SessionMessage(
        role=MessageRole.USER,
        content="Create a Python application.",
    )

    assert isinstance(message.id, UUID)
    assert message.role == MessageRole.USER
    assert message.content == "Create a Python application."
    assert message.metadata == {}


def test_message_accepts_role_string() -> None:
    message = SessionMessage(
        role="assistant",
        content="Hello!",
    )

    assert message.role == MessageRole.ASSISTANT


def test_message_rejects_negative_tokens() -> None:
    with pytest.raises(ValueError):
        SessionMessage(
            role=MessageRole.USER,
            content="Hello",
            token_count=-1,
        )


def test_add_message_updates_session(session: CodingSession) -> None:
    message = SessionMessage(
        role=MessageRole.USER,
        content="Build an API.",
        token_count=15,
    )

    previous_updated_at = session.updated_at
    session.add_message(message)

    assert len(session.messages) == 1
    assert session.total_tokens == 15
    assert session.updated_at >= previous_updated_at


def test_add_message_without_token_count(
    session: CodingSession,
) -> None:
    message = SessionMessage(
        role=MessageRole.USER,
        content="Hello",
    )

    session.add_message(message)

    assert session.total_tokens == 0
    assert len(session.messages) == 1


def test_remove_message(session: CodingSession) -> None:
    message = SessionMessage(
        role=MessageRole.ASSISTANT,
        content="Implementation complete.",
        token_count=25,
    )

    session.add_message(message)

    assert session.remove_message(message.id) is True
    assert session.messages == []
    assert session.total_tokens == 0


def test_remove_unknown_message(session: CodingSession) -> None:
    assert session.remove_message(SessionMessage(
        role=MessageRole.USER,
        content="Temporary",
    ).id) is False


def test_update_session_status(session: CodingSession) -> None:
    session.update_status(SessionStatus.PAUSED)

    assert session.status == SessionStatus.PAUSED

    session.update_status("completed")

    assert session.status == SessionStatus.COMPLETED


def test_touch_updates_timestamp(session: CodingSession) -> None:
    previous = session.updated_at - timedelta(seconds=1)

    session.touch()

    assert session.updated_at >= previous


def test_session_rejects_empty_workspace() -> None:
    with pytest.raises(ValueError):
        CodingSession(workspace="   ")


def test_session_rejects_empty_title() -> None:
    with pytest.raises(ValueError):
        CodingSession(
            workspace="C:/projects/demo",
            title="   ",
        )


def test_session_rejects_negative_tokens() -> None:
    with pytest.raises(ValueError):
        CodingSession(
            workspace="C:/projects/demo",
            total_tokens=-5,
        )


def test_message_serialization() -> None:
    original = SessionMessage(
        role=MessageRole.ASSISTANT,
        content="Hello FORGEX",
        metadata={"source": "test"},
        token_count=12,
        tool_name="test_tool",
    )

    restored = SessionMessage.from_dict(original.to_dict())

    assert restored.id == original.id
    assert restored.role == original.role
    assert restored.content == original.content
    assert restored.metadata == original.metadata
    assert restored.token_count == original.token_count
    assert restored.tool_name == original.tool_name


def test_session_serialization(session: CodingSession) -> None:
    session.add_message(
        SessionMessage(
            role=MessageRole.USER,
            content="Build a CLI.",
            token_count=10,
        )
    )

    restored = CodingSession.from_dict(session.to_dict())

    assert restored.id == session.id
    assert restored.workspace == session.workspace
    assert restored.title == session.title
    assert restored.status == session.status
    assert restored.total_tokens == session.total_tokens
    assert len(restored.messages) == 1
    assert restored.messages[0].content == "Build a CLI."


def test_session_serialization_without_messages(
    session: CodingSession,
) -> None:
    data = session.to_dict(include_messages=False)

    assert "messages" not in data

    restored = CodingSession.from_dict({
        **data,
        "messages": [],
    })

    assert restored.id == session.id
    assert restored.messages == []


def test_utc_now_is_timezone_aware() -> None:
    timestamp = utc_now()

    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() == timedelta(0)


def test_session_status_values() -> None:
    assert {status.value for status in SessionStatus} == {
        "active",
        "paused",
        "completed",
        "failed",
        "archived",
    }
