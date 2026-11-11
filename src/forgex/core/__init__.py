"""Core architecture and public API for FORGEX."""

from forgex.core.application import ForgexApplication
from forgex.core.context import ApplicationContext
from forgex.core.events import EventBus, EventType, ForgexEvent
from forgex.core.exceptions import (
    AgentError,
    ConfigurationError,
    ContextError,
    ExecutionError,
    ForgexError,
    InitializationError,
    ModelError,
    PermissionDeniedError,
    SecurityError,
    SessionError,
    StorageError,
    TaskCancelledError,
    ToolExecutionError,
)
from forgex.core.lifecycle import (
    ApplicationLifecycle,
    ApplicationState,
)
from forgex.core.orchestrator import (
    ForgexState,
    WorkflowOrchestrator,
)
from forgex.core.task import (
    ForgexTask,
    TaskManager,
    TaskProgress,
    TaskStatus,
)

__all__ = [
    # Application
    "ForgexApplication",
    # Context
    "ApplicationContext",
    # Events
    "EventBus",
    "EventType",
    "ForgexEvent",
    # Exceptions
    "ForgexError",
    "ConfigurationError",
    "InitializationError",
    "ExecutionError",
    "AgentError",
    "ModelError",
    "ToolExecutionError",
    "SecurityError",
    "PermissionDeniedError",
    "SessionError",
    "StorageError",
    "ContextError",
    "TaskCancelledError",
    # Lifecycle
    "ApplicationLifecycle",
    "ApplicationState",
    # Orchestration
    "ForgexState",
    "WorkflowOrchestrator",
    # Tasks
    "ForgexTask",
    "TaskManager",
    "TaskProgress",
    "TaskStatus",
]
