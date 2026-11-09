"""Interactive slash commands for the FORGEX CLI."""

__all__: list[str] = []
"""FORGEX interactive slash command system."""

from forgex.cli.slash_commands.builtin import (
    create_builtin_registry,
    register_builtin_commands,
)
from forgex.cli.slash_commands.registry import (
    SlashCommand,
    SlashCommandRegistry,
    SlashCommandResult,
)

__all__ = [
    "SlashCommand",
    "SlashCommandRegistry",
    "SlashCommandResult",
    "create_builtin_registry",
    "register_builtin_commands",
]
