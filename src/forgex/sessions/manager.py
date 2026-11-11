"""Session lifecycle and message management for FORGEX."""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Protocol
from uuid import UUID

from forgex.core.exceptions import SessionError
from forgex.sessions.models import (
    CodingSession,
    MessageRole,
    SessionMessage,
    SessionStatus,
)


class SessionNotFoundError(SessionError):
    """Raised when a requested session does not exist."""


class SessionAlreadyExistsError(SessionError):
    """Raised when attempting to create a duplicate session."""


class InvalidSessionOperationError(SessionError):
    """Raised when a session operation is not valid for its state."""


class SessionRepository(Protocol):
    """Storage interface required by SessionManager."""

    def create(self, session: CodingSession) -> None:
        """Persist a new session."""

    def get(self, session_id: str) -> CodingSession | None:
        """Retrieve a session by ID."""

    def list(
        self,
        *,
        workspace: str | None = None,
        status: SessionStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CodingSession]:
        """Retrieve sessions using optional filters."""

    def save(self, session: CodingSession) -> None:
        """Persist changes to an existing session."""

    def delete(self, session_id: str) -> bool:
        """Delete a session."""


class InMemorySessionRepository:
    """Thread-safe in-memory session repository.

    This repository is intended as a default backend and for testing.
    Use a persistent repository for production session durability.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, CodingSession] = {}
        self._lock = threading.RLock()

    def create(self, session: CodingSession) -> None:
        session_id = str(session.id)

        with self._lock:
            if session_id in self._sessions:
                raise SessionAlreadyExistsError(f"Session '{session_id}' already exists.")

            self._sessions[session_id] = deepcopy(session)

    def get(self, session_id: str) -> CodingSession | None:
        with self._lock:
            session = self._sessions.get(str(session_id))
            return deepcopy(session) if session is not None else None

    def list(
        self,
        *,
        workspace: str | None = None,
        status: SessionStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CodingSession]:
        if offset < 0:
            raise ValueError("offset cannot be negative.")

        if limit is not None and limit < 0:
            raise ValueError("limit cannot be negative.")

        with self._lock:
            sessions = list(self._sessions.values())

            if workspace is not None:
                sessions = [item for item in sessions if item.workspace == workspace]

            if status is not None:
                sessions = [item for item in sessions if item.status == status]

            sessions.sort(
                key=lambda item: item.updated_at,
                reverse=True,
            )

            sessions = sessions[offset:]

            if limit is not None:
                sessions = sessions[:limit]

            return deepcopy(sessions)

    def save(self, session: CodingSession) -> None:
        session_id = str(session.id)

        with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(f"Session '{session_id}' does not exist.")

            self._sessions[session_id] = deepcopy(session)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(str(session_id), None) is not None


class SessionManager:
    """Manage coding sessions and their conversation history."""

    def __init__(
        self,
        repository: SessionRepository | None = None,
    ) -> None:
        self._repository = repository or InMemorySessionRepository()
        self._lock = threading.RLock()

    @staticmethod
    def _normalize_id(session_id: str | UUID) -> str:
        """Normalize session identifiers."""

        try:
            return str(UUID(str(session_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise SessionNotFoundError(f"Invalid session ID: '{session_id}'.") from exc

    def create_session(
        self,
        workspace: str,
        title: str = "New coding session",
        *,
        metadata: dict | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> CodingSession:
        """Create and register a new coding session."""

        if not workspace or not workspace.strip():
            raise ValueError("workspace cannot be empty.")

        session = CodingSession(
            workspace=workspace,
            title=title,
            metadata=dict(metadata or {}),
            model_provider=model_provider,
            model_name=model_name,
        )

        with self._lock:
            self._repository.create(session)

        return session

    def get_session(
        self,
        session_id: str | UUID,
    ) -> CodingSession:
        """Retrieve a session or raise SessionNotFoundError."""

        normalized_id = self._normalize_id(session_id)
        session = self._repository.get(normalized_id)

        if session is None:
            raise SessionNotFoundError(f"Session '{normalized_id}' was not found.")

        return session

    def find_session(
        self,
        session_id: str | UUID,
    ) -> CodingSession | None:
        """Retrieve a session without raising when it is missing."""

        try:
            normalized_id = self._normalize_id(session_id)
        except SessionNotFoundError:
            return None

        return self._repository.get(normalized_id)

    def list_sessions(
        self,
        *,
        workspace: str | None = None,
        status: SessionStatus | None = None,
        limit: int | None = 50,
        offset: int = 0,
    ) -> list[CodingSession]:
        """List sessions, optionally filtered by workspace or status."""

        return self._repository.list(
            workspace=workspace,
            status=status,
            limit=limit,
            offset=offset,
        )

    def search_sessions(
        self,
        query: str,
        *,
        workspace: str | None = None,
        limit: int | None = 50,
    ) -> list[CodingSession]:
        """Search session titles, messages, and metadata."""

        if not query or not query.strip():
            return []

        if limit is not None and limit < 0:
            raise ValueError("limit cannot be negative.")

        normalized_query = query.casefold().strip()

        sessions = self._repository.list(workspace=workspace)

        matches: list[CodingSession] = []

        for session in sessions:
            searchable_text = [
                session.title,
                session.workspace,
                str(session.metadata),
            ]

            searchable_text.extend(message.content for message in session.messages)

            if any(normalized_query in text.casefold() for text in searchable_text):
                matches.append(session)

                if limit is not None and len(matches) >= limit:
                    break

        return matches

    def update_session(
        self,
        session: CodingSession,
    ) -> CodingSession:
        """Persist changes to an existing session."""

        existing = self.get_session(session.id)

        if existing.id != session.id:
            raise SessionNotFoundError(f"Session '{session.id}' was not found.")

        session.touch()
        self._repository.save(session)

        return deepcopy(session)

    def rename_session(
        self,
        session_id: str | UUID,
        title: str,
    ) -> CodingSession:
        """Change a session's title."""

        if not title or not title.strip():
            raise ValueError("Session title cannot be empty.")

        session = self.get_session(session_id)
        session.title = title.strip()
        return self.update_session(session)

    def update_metadata(
        self,
        session_id: str | UUID,
        metadata: dict,
        *,
        merge: bool = True,
    ) -> CodingSession:
        """Update session metadata."""

        session = self.get_session(session_id)

        if merge:
            session.metadata.update(metadata)
        else:
            session.metadata = dict(metadata)

        return self.update_session(session)

    def pause_session(
        self,
        session_id: str | UUID,
    ) -> CodingSession:
        """Pause an active session."""

        return self._change_status(
            session_id,
            SessionStatus.PAUSED,
            allowed_from={SessionStatus.ACTIVE},
        )

    def resume_session(
        self,
        session_id: str | UUID,
    ) -> CodingSession:
        """Resume a paused session."""

        return self._change_status(
            session_id,
            SessionStatus.ACTIVE,
            allowed_from={SessionStatus.PAUSED},
        )

    def complete_session(
        self,
        session_id: str | UUID,
    ) -> CodingSession:
        """Mark a session as completed."""

        return self._change_status(
            session_id,
            SessionStatus.COMPLETED,
            allowed_from={
                SessionStatus.ACTIVE,
                SessionStatus.PAUSED,
            },
        )

    def fail_session(
        self,
        session_id: str | UUID,
    ) -> CodingSession:
        """Mark a session as failed."""

        return self._change_status(
            session_id,
            SessionStatus.FAILED,
            allowed_from={
                SessionStatus.ACTIVE,
                SessionStatus.PAUSED,
            },
        )

    def archive_session(
        self,
        session_id: str | UUID,
    ) -> CodingSession:
        """Archive a completed or failed session."""

        return self._change_status(
            session_id,
            SessionStatus.ARCHIVED,
            allowed_from={
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
            },
        )

    def _change_status(
        self,
        session_id: str | UUID,
        new_status: SessionStatus,
        *,
        allowed_from: set[SessionStatus],
    ) -> CodingSession:
        """Validate and persist a session status transition."""

        with self._lock:
            session = self.get_session(session_id)

            if session.status not in allowed_from:
                raise InvalidSessionOperationError(
                    f"Cannot change session status from "
                    f"'{session.status.value}' to '{new_status.value}'."
                )

            session.update_status(new_status)
            self._repository.save(session)

            return deepcopy(session)

    def add_message(
        self,
        session_id: str | UUID,
        content: str,
        *,
        role: MessageRole = MessageRole.USER,
        metadata: dict | None = None,
        token_count: int = 0,
        tool_name: str | None = None,
    ) -> SessionMessage:
        """Append a message to an active or paused session."""

        with self._lock:
            session = self.get_session(session_id)

            if session.status not in {
                SessionStatus.ACTIVE,
                SessionStatus.PAUSED,
            }:
                raise InvalidSessionOperationError(
                    f"Messages cannot be added to a {session.status.value} session."
                )

            message = SessionMessage(
                content=content,
                role=role,
                metadata=dict(metadata or {}),
                token_count=token_count,
                tool_name=tool_name,
            )

            session.add_message(message)
            self._repository.save(session)

            return deepcopy(message)

    def get_messages(
        self,
        session_id: str | UUID,
        *,
        limit: int | None = None,
    ) -> list[SessionMessage]:
        """Retrieve conversation messages in chronological order."""

        if limit is not None and limit < 0:
            raise ValueError("limit cannot be negative.")

        session = self.get_session(session_id)
        messages = session.messages

        if limit is not None:
            messages = messages[-limit:] if limit else []

        return deepcopy(messages)

    def remove_message(
        self,
        session_id: str | UUID,
        message_id: str | UUID,
    ) -> SessionMessage:
        """Remove a message from a session."""

        session = self.get_session(session_id)
        normalized_message_id = str(message_id)

        for message in session.messages:
            if str(message.id) == normalized_message_id:
                session.remove_message(message.id)
                self.update_session(session)
                return deepcopy(message)

        raise SessionError(f"Message '{normalized_message_id}' was not found.")

    def clear_messages(
        self,
        session_id: str | UUID,
    ) -> int:
        """Remove all messages and return the number removed."""

        session = self.get_session(session_id)
        removed_count = len(session.messages)

        session.messages.clear()
        session.total_tokens = 0
        session.touch()

        self._repository.save(session)

        return removed_count

    def delete_session(
        self,
        session_id: str | UUID,
    ) -> bool:
        """Permanently delete a session."""

        normalized_id = self._normalize_id(session_id)

        with self._lock:
            if self._repository.get(normalized_id) is None:
                return False

            return self._repository.delete(normalized_id)

    def get_session_count(
        self,
        *,
        workspace: str | None = None,
        status: SessionStatus | None = None,
    ) -> int:
        """Return the number of matching sessions."""

        return len(
            self._repository.list(
                workspace=workspace,
                status=status,
            )
        )

    def get_recent_sessions(
        self,
        *,
        workspace: str | None = None,
        limit: int = 10,
    ) -> list[CodingSession]:
        """Return the most recently updated sessions."""

        return self.list_sessions(
            workspace=workspace,
            limit=limit,
        )
