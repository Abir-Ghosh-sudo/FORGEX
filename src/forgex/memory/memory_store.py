"""Memory store interfaces and data models."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryItem:
    """A single memory item."""

    id: str
    content: str
    memory_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    embedding: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "embedding": self.embedding,
        }


@dataclass(slots=True)
class MemorySearchResult:
    """A search result from a memory store."""

    item: MemoryItem
    score: float


class MemoryStore:
    """Abstract memory store interface."""

    async def add(self, item: MemoryItem) -> str:
        raise NotImplementedError

    async def search(self, query: str, *, limit: int = 10) -> list[MemorySearchResult]:
        raise NotImplementedError

    async def get(self, memory_id: str) -> MemoryItem | None:
        raise NotImplementedError

    async def delete(self, memory_id: str) -> bool:
        raise NotImplementedError

    async def clear(self) -> bool:
        raise NotImplementedError

    async def close(self) -> None:
        """Release store resources."""


__all__ = ["MemoryStore", "MemoryItem", "MemorySearchResult"]
