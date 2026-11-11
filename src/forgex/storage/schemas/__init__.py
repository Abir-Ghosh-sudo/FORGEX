
"""Database schema definitions for FORGEX."""

from .memory import (
    CREATE_MEMORY_CHUNKS_TABLE,
    CREATE_MEMORY_ENTRIES_TABLE,
    CREATE_MEMORY_INDEXES,
    create_memory_schema,
)
from .session import (
    CREATE_SESSION_INDEXES,
    CREATE_SESSION_MESSAGES_TABLE,
    CREATE_SESSIONS_TABLE,
    create_session_schema,
)

__all__ = [
    "CREATE_MEMORY_CHUNKS_TABLE",
    "CREATE_MEMORY_ENTRIES_TABLE",
    "CREATE_MEMORY_INDEXES",
    "create_memory_schema",
    "CREATE_SESSION_MESSAGES_TABLE",
    "CREATE_SESSIONS_TABLE",
    "CREATE_SESSION_INDEXES",
    "create_session_schema",
]
