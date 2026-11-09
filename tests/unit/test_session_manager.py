
"""Unit tests for FORGEX session management."""

from uuid import UUID

import pytest

from forgex.core.exceptions import SessionError
from forgex.sessions import (
    InvalidSessionOperationError,
    SessionManager,
    SessionNotFoundError,
    SessionStatus,
)


@pytest.fixture
def manager() -> SessionManager:
    """Create an isolated session manager for each test."""
    return SessionManager()


@pytest.fixture
def session(manager: SessionManager):
    """Create a sample coding session."""
    return manager.create_session(
        workspace="C:/projects/sample",
        title="Test Session",
    )


class TestSessionCreation:
    def test_create_session(self, manager: SessionManager):
        session = manager.create_session(
            workspace="C:/projects/demo",
            title="Demo Session",
        )

        assert session.title == "Demo Session"
        assert session.workspace == "C:/projects/demo"
        assert session.status == SessionStatus.ACTIVE
        assert isinstance(session.id, UUID)

    def test_create_session_with_metadata(self, manager: SessionManager):
        session = manager.create_session(
            workspace="/projects/demo",
            metadata={"branch": "main"},
            model_provider="ollama",
            model_name="qwen2.5-coder:7b",
        )

        assert session.metadata["branch"] == "main"
        assert session.model_provider == "ollama"
        assert session.model_name == "qwen2.5-coder:7b"

    def test_empty_workspace_is_rejected(self, manager: SessionManager):
        with pytest.raises(ValueError):
            manager.create_session(workspace=" ")

    def test_created_session_can_be_retrieved(
        self,
        manager: SessionManager,
        session,
    ):
        retrieved = manager.get_session(session.id)

        assert retrieved.id == session.id
        assert retrieved.title == session.title

    def test_invalid_session_id_raises(self, manager: SessionManager):
        with pytest.raises(SessionNotFoundError):
            manager.get_session("invalid-id")

    def test_missing_session_raises(self, manager: SessionManager):
        with pytest.raises(SessionNotFoundError):
            manager.get_session(UUID("00000000-0000-0000-0000-000000000001"))

    def test_find_missing_session_returns_none(
        self,
        manager: SessionManager,
    ):
        assert manager.find_session("invalid-id") is None


class TestSessionListing:
    def test_list_sessions(self, manager: SessionManager):
        manager.create_session("/project/a", "Session A")
        manager.create_session("/project/b", "Session B")

        sessions = manager.list_sessions()

        assert len(sessions) == 2

    def test_filter_by_workspace(self, manager: SessionManager):
        manager.create_session("/project/a", "Session A")
        manager.create_session("/project/b", "Session B")

        sessions = manager.list_sessions(workspace="/project/a")

        assert len(sessions) == 1
        assert sessions[0].workspace == "/project/a"

    def test_filter_by_status(
        self,
        manager: SessionManager,
    ):
        active = manager.create_session("/project", "Active")
        completed = manager.create_session("/project", "Completed")

        manager.complete_session(completed.id)

        sessions = manager.list_sessions(status=SessionStatus.ACTIVE)

        assert len(sessions) == 1
        assert sessions[0].id == active.id

    def test_list_with_limit_and_offset(self, manager: SessionManager):
        for index in range(5):
            manager.create_session("/project", f"Session {index}")

        sessions = manager.list_sessions(limit=2, offset=1)

        assert len(sessions) == 2

    def test_negative_offset_is_rejected(self, manager: SessionManager):
        with pytest.raises(ValueError):
            manager.list_sessions(offset=-1)

    def test_negative_limit_is_rejected(self, manager: SessionManager):
        with pytest.raises(ValueError):
            manager.list_sessions(limit=-1)

    def test_search_by_title(self, manager: SessionManager):
        manager.create_session("/project", "Authentication Module")
        manager.create_session("/project", "Payment Module")

        results = manager.search_sessions("authentication")

        assert len(results) == 1
        assert results[0].title == "Authentication Module"

    def test_search_by_message(self, manager: SessionManager):
        session = manager.create_session("/project", "Development")

        manager.add_message(
            session.id,
            "Implement JWT authentication",
        )

        results = manager.search_sessions("jwt")

        assert len(results) == 1

    def test_search_is_case_insensitive(self, manager: SessionManager):
        manager.create_session("/project", "FORGEX Development")

        assert len(manager.search_sessions("forgex")) == 1

    def test_empty_search_returns_empty_list(
        self,
        manager: SessionManager,
    ):
        manager.create_session("/project", "Development")

        assert manager.search_sessions(" ") == []


class TestSessionUpdates:
    def test_rename_session(
        self,
        manager: SessionManager,
        session,
    ):
        updated = manager.rename_session(session.id, "New Title")

        assert updated.title == "New Title"

    def test_empty_title_is_rejected(
        self,
        manager: SessionManager,
        session,
    ):
        with pytest.raises(ValueError):
            manager.rename_session(session.id, " ")

    def test_update_metadata(
        self,
        manager: SessionManager,
        session,
    ):
        manager.update_metadata(
            session.id,
            {"branch": "feature/auth"},
        )

        updated = manager.get_session(session.id)

        assert updated.metadata["branch"] == "feature/auth"

    def test_replace_metadata(
        self,
        manager: SessionManager,
        session,
    ):
        manager.update_metadata(
            session.id,
            {"old": "value"},
        )

        manager.update_metadata(
            session.id,
            {"new": "value"},
            merge=False,
        )

        updated = manager.get_session(session.id)

        assert updated.metadata == {"new": "value"}


class TestSessionLifecycle:
    def test_pause_session(
        self,
        manager: SessionManager,
        session,
    ):
        paused = manager.pause_session(session.id)

        assert paused.status == SessionStatus.PAUSED

    def test_resume_session(
        self,
        manager: SessionManager,
        session,
    ):
        manager.pause_session(session.id)

        resumed = manager.resume_session(session.id)

        assert resumed.status == SessionStatus.ACTIVE

    def test_complete_session(
        self,
        manager: SessionManager,
        session,
    ):
        completed = manager.complete_session(session.id)

        assert completed.status == SessionStatus.COMPLETED

    def test_fail_session(
        self,
        manager: SessionManager,
        session,
    ):
        failed = manager.fail_session(session.id)

        assert failed.status == SessionStatus.FAILED

    def test_archive_completed_session(
        self,
        manager: SessionManager,
        session,
    ):
        manager.complete_session(session.id)

        archived = manager.archive_session(session.id)

        assert archived.status == SessionStatus.ARCHIVED

    def test_cannot_resume_active_session(
        self,
        manager: SessionManager,
        session,
    ):
        with pytest.raises(InvalidSessionOperationError):
            manager.resume_session(session.id)

    def test_cannot_pause_completed_session(
        self,
        manager: SessionManager,
        session,
    ):
        manager.complete_session(session.id)

        with pytest.raises(InvalidSessionOperationError):
            manager.pause_session(session.id)

    def test_cannot_archive_active_session(
        self,
        manager: SessionManager,
        session,
    ):
        with pytest.raises(InvalidSessionOperationError):
            manager.archive_session(session.id)

    def test_cannot_add_message_to_completed_session(
        self,
        manager: SessionManager,
        session,
    ):
        manager.complete_session(session.id)

        with pytest.raises(InvalidSessionOperationError):
            manager.add_message(session.id, "Another message")


class TestSessionMessages:
    def test_add_message(
        self,
        manager: SessionManager,
        session,
    ):
        message = manager.add_message(
            session.id,
            "Hello FORGEX",
        )

        assert message.content == "Hello FORGEX"

    def test_add_message_with_role(
        self,
        manager: SessionManager,
        session,
    ):
        from forgex.sessions import MessageRole

        message = manager.add_message(
            session.id,
            "Generated response",
            role=MessageRole.ASSISTANT,
            token_count=12,
        )

        assert message.role == MessageRole.ASSISTANT
        assert message.token_count == 12

    def test_get_messages(
        self,
        manager: SessionManager,
        session,
    ):
        manager.add_message(session.id, "First")
        manager.add_message(session.id, "Second")

        messages = manager.get_messages(session.id)

        assert len(messages) == 2
        assert messages[0].content == "First"
        assert messages[1].content == "Second"

    def test_get_messages_with_limit(
        self,
        manager: SessionManager,
        session,
    ):
        manager.add_message(session.id, "First")
        manager.add_message(session.id, "Second")
        manager.add_message(session.id, "Third")

        messages = manager.get_messages(session.id, limit=2)

        assert len(messages) == 2
        assert messages[0].content == "Second"

    def test_clear_messages(
        self,
        manager: SessionManager,
        session,
    ):
        manager.add_message(session.id, "First", token_count=10)
        manager.add_message(session.id, "Second", token_count=20)

        removed = manager.clear_messages(session.id)

        updated = manager.get_session(session.id)

        assert removed == 2
        assert updated.messages == []
        assert updated.total_tokens == 0

    def test_remove_message(
        self,
        manager: SessionManager,
        session,
    ):
        message = manager.add_message(session.id, "Remove me")

        removed = manager.remove_message(session.id, message.id)

        assert removed.id == message.id
        assert manager.get_messages(session.id) == []

    def test_remove_missing_message_raises(
        self,
        manager: SessionManager,
        session,
    ):
        with pytest.raises(SessionError):
            manager.remove_message(
                session.id,
                "00000000-0000-0000-0000-000000000001",
            )


class TestSessionDeletionAndCounts:
    def test_delete_session(
        self,
        manager: SessionManager,
        session,
    ):
        assert manager.delete_session(session.id) is True
        assert manager.find_session(session.id) is None

    def test_delete_missing_session_returns_false(
        self,
        manager: SessionManager,
    ):
        assert manager.delete_session(
            "00000000-0000-0000-0000-000000000001"
        ) is False

    def test_session_count(self, manager: SessionManager):
        manager.create_session("/project", "One")
        manager.create_session("/project", "Two")

        assert manager.get_session_count() == 2

    def test_count_by_status(self, manager: SessionManager):
        manager.create_session("/project", "Active")
        completed = manager.create_session("/project", "Completed")

        manager.complete_session(completed.id)

        assert manager.get_session_count(
            status=SessionStatus.ACTIVE
        ) == 1

    def test_recent_sessions(self, manager: SessionManager):
        for index in range(3):
            manager.create_session("/project", f"Session {index}")

        sessions = manager.get_recent_sessions(limit=2)

        assert len(sessions) == 2


class TestRepositoryIsolation:
    def test_returned_session_does_not_mutate_storage(
        self,
        manager: SessionManager,
        session,
    ):
        retrieved = manager.get_session(session.id)
        retrieved.title = "External Mutation"

        stored = manager.get_session(session.id)

        assert stored.title == "Test Session"

    def test_returned_message_does_not_mutate_storage(
        self,
        manager: SessionManager,
        session,
    ):
        message = manager.add_message(session.id, "Original")

        message.content = "Changed externally"

        stored = manager.get_messages(session.id)

        assert stored[0].content == "Original"
