"""Domain models for FORGEX coding sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


class SessionStatus(StrEnum):
    """Lifecycle states of a coding session."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    """Supported conversation message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(slots=True)
class SessionMessage:
    """A single message stored in a coding session."""

    content: str
    role: MessageRole
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int | None = None
    tool_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("Message content must be a string.")

        if not isinstance(self.role, MessageRole):
            self.role = MessageRole(self.role)

        if self.token_count is not None and self.token_count < 0:
            raise ValueError("Token count cannot be negative.")

        if self.created_at.tzinfo is None:
            raise ValueError("Message timestamp must be timezone-aware.")

    def to_dict(self) -> dict[str, Any]:
        """Convert the message into a JSON-compatible dictionary."""

        return {
            "id": str(self.id),
            "role": self.role.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "token_count": self.token_count,
            "tool_name": self.tool_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMessage:
        """Restore a message from serialized data."""

        return cls(
            id=UUID(data["id"]),
            role=MessageRole(data["role"]),
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=dict(data.get("metadata") or {}),
            token_count=data.get("token_count"),
            tool_name=data.get("tool_name"),
        )


@dataclass(slots=True)
class CodingSession:
    """Persistent state and conversation history of a coding session."""

    workspace: str
    title: str = "New Coding Session"
    id: UUID = field(default_factory=uuid4)
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    messages: list[SessionMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    model_provider: str | None = None
    model_name: str | None = None
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if not self.workspace.strip():
            raise ValueError("Session workspace cannot be empty.")

        if not self.title.strip():
            raise ValueError("Session title cannot be empty.")

        if not isinstance(self.status, SessionStatus):
            self.status = SessionStatus(self.status)

        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Session timestamps must be timezone-aware.")

        if self.total_tokens < 0:
            raise ValueError("Total token count cannot be negative.")

    def add_message(self, message: SessionMessage) -> None:
        """Append a message and update session statistics."""

        self.messages.append(message)

        if message.token_count is not None:
            self.total_tokens += message.token_count

        self.updated_at = utc_now()

    def remove_message(self, message_id: UUID) -> bool:
        """Remove a message by ID and update token statistics."""

        for index, message in enumerate(self.messages):
            if message.id == message_id:
                if message.token_count is not None:
                    self.total_tokens -= message.token_count

                del self.messages[index]
                self.updated_at = utc_now()
                return True

        return False

    def update_status(self, status: SessionStatus) -> None:
        """Change the session lifecycle status."""

        if not isinstance(status, SessionStatus):
            status = SessionStatus(status)

        self.status = status
        self.updated_at = utc_now()

    def touch(self) -> None:
        """Update the last-modified timestamp."""

        self.updated_at = utc_now()

    def to_dict(self, include_messages: bool = True) -> dict[str, Any]:
        """Convert the session into a JSON-compatible dictionary."""

        result = {
            "id": str(self.id),
            "workspace": self.workspace,
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "total_tokens": self.total_tokens,
        }

        if include_messages:
            result["messages"] = [message.to_dict() for message in self.messages]

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodingSession:
        """Restore a complete session from serialized data."""

        return cls(
            id=UUID(data["id"]),
            workspace=data["workspace"],
            title=data.get("title", "New Coding Session"),
            status=SessionStatus(data.get("status", "active")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            messages=[SessionMessage.from_dict(message) for message in data.get("messages", [])],
            metadata=dict(data.get("metadata") or {}),
            model_provider=data.get("model_provider"),
            model_name=data.get("model_name"),
            total_tokens=data.get("total_tokens", 0),
        )
