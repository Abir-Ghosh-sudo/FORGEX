"""Central exception definitions for FORGEX."""

from __future__ import annotations


class ForgexError(Exception):
    """Base exception for all FORGEX application errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "FORGEX_ERROR",
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigurationError(ForgexError):
    """Raised when application configuration is invalid."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", **kwargs)


class InitializationError(ForgexError):
    """Raised when a component cannot initialize."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="INITIALIZATION_ERROR", **kwargs)


class ExecutionError(ForgexError):
    """Raised when a task or operation fails."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="EXECUTION_ERROR", **kwargs)


class AgentError(ForgexError):
    """Raised when an AI agent encounters an error."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="AGENT_ERROR", **kwargs)


class ModelError(ForgexError):
    """Raised when a model provider or inference operation fails."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="MODEL_ERROR", **kwargs)


class ToolExecutionError(ForgexError):
    """Raised when a tool operation fails."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="TOOL_EXECUTION_ERROR", **kwargs)


class SecurityError(ForgexError):
    """Raised when a security policy is violated."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="SECURITY_ERROR", **kwargs)


class PermissionDeniedError(SecurityError):
    """Raised when an operation is not authorized."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, **kwargs)


class SessionError(ForgexError):
    """Raised when session management fails."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="SESSION_ERROR", **kwargs)


class StorageError(ForgexError):
    """Raised when persistent storage operations fail."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="STORAGE_ERROR", **kwargs)


class ContextError(ForgexError):
    """Raised when repository or context processing fails."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message, code="CONTEXT_ERROR", **kwargs)


class TaskCancelledError(ForgexError):
    """Raised when a task is cancelled."""

    def __init__(self, message: str = "Task was cancelled.") -> None:
        super().__init__(message, code="TASK_CANCELLED")
