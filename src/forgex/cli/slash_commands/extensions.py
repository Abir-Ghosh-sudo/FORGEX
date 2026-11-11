"""Slash command extensions: /plan, /approve, /reject, /context, /compact, /tools, /skills."""

from __future__ import annotations

import typer
from rich.console import Console

from forgex.cli.slash_commands.registry import slash_registry
from forgex.cli.slash_commands.builtin import SlashCommand

console = Console()


def register_extended_slash_commands() -> None:
    """Register extended slash commands."""

    @slash_registry.register("plan")
    def slash_plan(args: str) -> str:
        """Show or create a task plan."""
        return "/plan: Use /run to start a task. The planner agent creates plans automatically."

    @slash_registry.register("approve")
    def slash_approve(args: str) -> str:
        """Approve a pending action."""
        return "/approve: Approval granted for the pending action."

    @slash_registry.register("reject")
    def slash_reject(args: str) -> str:
        """Reject a pending action."""
        return "/reject: Action rejected."

    @slash_registry.register("context")
    def slash_context(args: str) -> str:
        """Show repository context summary."""
        return "/context: Repository context is gathered automatically during task execution."

    @slash_registry.register("compact")
    def slash_compact(args: str) -> str:
        """Compact conversation context."""
        return "/compact: Context compaction not yet implemented."

    @slash_registry.register("tools")
    def slash_tools(args: str) -> str:
        """List available tools."""
        return "/tools: Filesystem, terminal, git, testing, packages, memory, mcp, skills, plugins."

    @slash_registry.register("skills")
    def slash_skills(args: str) -> str:
        """List available skills."""
        return "/skills: coding, debugging, testing, refactoring."


__all__ = ["register_extended_slash_commands"]
