"""FORGEX terminal welcome screen."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

_LOGO = r"""
███████╗ ██████╗ ██████╗  ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝╚██╗██╔╝
█████╗  ██║   ██║██████╔╝██║  ███╗█████╗   ╚███╔╝
██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝   ██╔██╗
██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗██╔╝ ██╗
╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
"""


def show_welcome(console: Console | None = None, *, wait_for_enter: bool = True) -> None:
    """Render the branded startup screen and optionally wait for confirmation."""
    target = console or Console()
    target.clear()
    banner = Text.from_markup(
        "[orange1]✳[/orange1]  Welcome to the [bold]FORGEX[/bold] terminal coding agent!"
    )
    target.print(Panel(banner, border_style="orange1", padding=(1, 2), expand=False))
    target.print()
    target.print(Text(_LOGO, style="bold #e17b5c", no_wrap=True))
    target.print()
    target.print(
        "[bold #79aee8]Build Beyond Code.[/bold #79aee8]  "
        "[dim]Your workspace. Your models. Your agent.[/dim]"
    )
    if wait_for_enter:
        Prompt.ask(
            "[bold #79aee8]Press Enter to continue[/bold #79aee8]",
            console=target,
            default="",
            show_default=False,
        )


__all__ = ["show_welcome"]
