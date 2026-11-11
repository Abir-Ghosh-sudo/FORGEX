"""Slash command registration, parsing, and dispatch for FORGEX."""

from __future__ import annotations

import inspect
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SlashHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """Definition of a FORGEX slash command."""

    name: str
    description: str
    handler: SlashHandler
    aliases: tuple[str, ...] = ()
    usage: str = ""
    category: str = "general"

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError("Command name must be non-empty and contain no spaces.")

        if self.name.startswith("/"):
            raise ValueError("Command names must not start with '/'.")

        if not callable(self.handler):
            raise TypeError("Command handler must be callable.")

        if any(not alias or alias.startswith("/") for alias in self.aliases):
            raise ValueError("Aliases must be non-empty and must not start with '/'.")


@dataclass(slots=True)
class SlashCommandResult:
    """Result returned after slash command execution."""

    command: str
    success: bool
    message: str = ""
    data: Any = None
    error: Exception | None = None


@dataclass(slots=True)
class SlashCommandRegistry:
    """Register and execute slash commands."""

    commands: dict[str, SlashCommand] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    def register(self, command: str | SlashCommand) -> Any:
        """Register a command and its aliases.

        Can be used as a decorator with a name string:
            @registry.register("name")
            def handler(args): ...

        Or with a SlashCommand object:
            registry.register(SlashCommand(...))
        """

        if isinstance(command, str):

            def decorator(handler: SlashHandler) -> SlashHandler:
                cmd = SlashCommand(name=command, description=handler.__doc__ or "", handler=handler)
                self._register_cmd(cmd)
                return handler

            return decorator

        self._register_cmd(command)
        return command

    def _register_cmd(self, command: SlashCommand) -> None:
        names = (command.name, *command.aliases)

        for name in names:
            if name in self.commands or name in self._aliases:
                raise ValueError(f"Slash command already registered: /{name}")

        self.commands[command.name] = command

        for alias in command.aliases:
            self._aliases[alias] = command.name

    def unregister(self, name: str) -> bool:
        """Remove a command by its name or alias."""

        canonical_name = self._aliases.get(name, name)
        command = self.commands.pop(canonical_name, None)

        if command is None:
            return False

        for alias in command.aliases:
            self._aliases.pop(alias, None)

        return True

    def get(self, name: str) -> SlashCommand | None:
        """Find a command by name or alias."""

        canonical_name = self._aliases.get(name, name)
        return self.commands.get(canonical_name)

    def list_commands(
        self,
        category: str | None = None,
    ) -> list[SlashCommand]:
        """Return registered commands, optionally filtered by category."""

        result = list(self.commands.values())

        if category is not None:
            result = [command for command in result if command.category == category]

        return sorted(result, key=lambda command: command.name)

    def parse(self, text: str) -> tuple[str, list[str]]:
        """Parse slash command text into a command name and arguments."""

        normalized = text.strip()

        if not normalized.startswith("/"):
            raise ValueError("Input is not a slash command.")

        try:
            parts = shlex.split(normalized[1:])
        except ValueError as exc:
            raise ValueError(f"Invalid command syntax: {exc}") from exc

        if not parts:
            raise ValueError("Empty slash command.")

        return parts[0].lower(), parts[1:]

    async def dispatch(self, text: str) -> SlashCommandResult:
        """Parse and execute a registered slash command."""

        try:
            name, arguments = self.parse(text)
        except ValueError as exc:
            return SlashCommandResult(
                command="",
                success=False,
                message=str(exc),
                error=exc,
            )

        command = self.get(name)

        if command is None:
            return SlashCommandResult(
                command=name,
                success=False,
                message=f"Unknown command: /{name}",
            )

        try:
            result = command.handler(*arguments)

            if inspect.isawaitable(result):
                result = await result

            return SlashCommandResult(
                command=command.name,
                success=True,
                data=result,
            )

        except Exception as exc:
            return SlashCommandResult(
                command=command.name,
                success=False,
                message=str(exc),
                error=exc,
            )

    def help_text(self, category: str | None = None) -> str:
        """Generate formatted help text for registered commands."""

        commands = self.list_commands(category)

        if not commands:
            return "No slash commands are registered."

        lines = ["FORGEX Slash Commands", ""]

        for command in commands:
            aliases = (
                f" (aliases: {', '.join('/' + alias for alias in command.aliases)})"
                if command.aliases
                else ""
            )

            usage = f" {command.usage}" if command.usage else ""

            lines.append(f"/{command.name}{usage}{aliases}\n    {command.description}")

        return "\n".join(lines)


slash_registry = SlashCommandRegistry()

__all__ = [
    "SlashHandler",
    "SlashCommand",
    "SlashCommandResult",
    "SlashCommandRegistry",
    "slash_registry",
]
