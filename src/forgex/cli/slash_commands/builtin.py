
"""Built-in slash commands for FORGEX interactive sessions."""

from __future__ import annotations

from typing import Any

from forgex.cli.slash_commands.registry import (
    SlashCommand,
    SlashCommandRegistry,
)


def _get_context_value(context: Any, key: str, default: Any = None) -> Any:
    """Read a value from a dictionary or an object."""

    if isinstance(context, dict):
        return context.get(key, default)

    return getattr(context, key, default)


async def _help_handler(
    registry: SlashCommandRegistry,
    context: Any = None,
) -> str:
    """Display registered slash commands."""

    return registry.help_text()


async def _clear_handler(context: Any = None) -> dict[str, Any]:
    """Request the interactive client to clear its conversation display."""

    callback = _get_context_value(context, "clear_callback")

    if callable(callback):
        result = callback()
        if hasattr(result, "__await__"):
            await result

    return {
        "action": "clear",
        "message": "Conversation display cleared.",
    }


async def _exit_handler(context: Any = None) -> dict[str, Any]:
    """Request the interactive client to exit."""

    callback = _get_context_value(context, "exit_callback")

    if callable(callback):
        result = callback()
        if hasattr(result, "__await__"):
            await result

    return {
        "action": "exit",
        "message": "Exit requested.",
    }


async def _status_handler(context: Any = None) -> dict[str, Any]:
    """Return the current interactive session status."""

    status_callback = _get_context_value(context, "status_callback")

    if callable(status_callback):
        result = status_callback()
        if hasattr(result, "__await__"):
            result = await result

        return result

    return {
        "session_id": _get_context_value(context, "session_id", "unknown"),
        "workspace": str(_get_context_value(context, "workspace", "unknown")),
        "status": _get_context_value(context, "status", "active"),
    }


async def _model_handler(context: Any = None) -> dict[str, Any]:
    """Return information about the active model."""

    model_callback = _get_context_value(context, "model_callback")

    if callable(model_callback):
        result = model_callback()
        if hasattr(result, "__await__"):
            result = await result

        return result

    return {
        "provider": _get_context_value(context, "model_provider", "unknown"),
        "model": _get_context_value(context, "model_name", "not configured"),
    }


def register_builtin_commands(
    registry: SlashCommandRegistry,
) -> SlashCommandRegistry:
    """Register all built-in FORGEX slash commands."""

    commands = [
        SlashCommand(
            name="help",
            description="Show available slash commands.",
            handler=lambda: _help_handler(registry),
            aliases=("h", "?"),
            usage="[command]",
            category="general",
        ),
        SlashCommand(
            name="clear",
            description="Clear the interactive conversation display.",
            handler=_clear_handler,
            aliases=("cls",),
            category="session",
        ),
        SlashCommand(
            name="exit",
            description="Exit the current interactive session.",
            handler=_exit_handler,
            aliases=("quit", "q"),
            category="session",
        ),
        SlashCommand(
            name="status",
            description="Show current session and workspace status.",
            handler=_status_handler,
            category="session",
        ),
        SlashCommand(
            name="model",
            description="Show information about the active AI model.",
            handler=_model_handler,
            category="models",
        ),
    ]

    for command in commands:
        registry.register(command)

    return registry


def create_builtin_registry() -> SlashCommandRegistry:
    """Create a registry containing all built-in commands."""

    registry = SlashCommandRegistry()
    return register_builtin_commands(registry)
