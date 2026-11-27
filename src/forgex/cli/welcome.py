"""FORGEX terminal welcome screen."""

from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

_ACCENT = "#8b7cf6"
_HIGHLIGHT = "#55d6c2"
_MUTED = "#9aa4b2"

_LOGO = r"""
  ▄████  ▒█████   ██▀███   ▄████ ▓█████ ▒██   ██▒
 ██▒ ▀█▒▒██▒  ██▒▓██ ▒ ██▒██▒ ▀█▒▓█   ▀ ▒▒ █ █ ▒░
▒██░▄▄▄░▒██░  ██▒▓██ ░▄█ ▒▒██░▄▄▄░▒███   ░░  █   ░
░▓█  ██▓▒██   ██░▒██▀▀█▄  ░▓█  ██▓▒▓█  ▄  ░ █ █ ▒
░▒▓███▀▒░ ████▓▒░░██▓ ▒██▒░▒▓███▀▒░▒████▒▒██▒ ▒██▒
 ░▒   ▒ ░ ▒░▒░▒░ ░ ▒▓ ░▒▓░ ░▒   ▒ ░░ ▒░ ░▒▒ ░ ░▓ ░
"""

def show_welcome(console: Console | None = None, *, wait_for_enter: bool = True) -> None:
    """Render the FORGEX terminal welcome screen."""
    target = console or Console()
    target.clear()

    eyebrow = Text("✦  FORGEX  /  AUTONOMOUS CODING WORKSPACE", style=f"bold {_HIGHLIGHT}")
    logo = Text(_LOGO, style=f"bold {_ACCENT}", no_wrap=True)
    tagline = Text("Build beyond the ordinary.", style=f"bold {_HIGHLIGHT}")
    description = Text("Plan  •  Code  •  Test  •  Improve", style=_MUTED)
    content = Group(
        Align.center(eyebrow),
        Text(""),
        Align.center(logo),
        Text(""),
        Align.center(tagline),
        Align.center(description),
    )
    target.print(
        Panel(
            content,
            title="[bold white]WELCOME[/bold white]",
            subtitle=f"[{_HIGHLIGHT}]YOUR AI DEVELOPMENT PARTNER[/{_HIGHLIGHT}]",
            border_style=_ACCENT,
            padding=(1, 3),
            expand=False,
        )
    )
    target.print()
    target.print(Align.center(Text("Press Enter to open your workspace", style=f"bold {_HIGHLIGHT}")))
    if wait_for_enter:
        Prompt.ask(
            f"[{_HIGHLIGHT}]Continue[/{_HIGHLIGHT}]",
            console=target,
            default="",
            show_default=False,
        )


__all__ = ["show_welcome"]
