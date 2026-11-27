"""FORGEX terminal welcome screen."""

from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

_ACCENT = "#B13CFF"  # FORGEX electric purple
_HIGHLIGHT = "#20DDF5"  # FORGEX neon cyan
_MUTED = "#A7B0C0"

_GLYPHS = {
    "F": ("█████", "██   ", "██   ", "████ ", "██   ", "██   ", "██   "),
    "O": (" ███ ", "██ ██", "██ ██", "██ ██", "██ ██", "██ ██", " ███ "),
    "R": ("████ ", "██ ██", "██ ██", "████ ", "███  ", "██ ██", "██ ██"),
    "G": (" ███ ", "██ ██", "██   ", "██ ██", "██ ██", "██ ██", " ███ "),
    "E": ("█████", "██   ", "██   ", "████ ", "██   ", "██   ", "█████"),
    "X": ("██ ██", "██ ██", " ██ █ ", "  █  ", " ██ █ ", "██ ██", "██ ██"),
}


def _build_wordmark() -> Group:
    """Build a large, terminal-native FORGEX wordmark."""
    rows: list[Text] = []
    letters = "FORGEX"
    for row_index in range(7):
        line = Text()
        for index, letter in enumerate(letters):
            if index:
                line.append("   ")
            color = _HIGHLIGHT if index % 2 == 0 else _ACCENT
            line.append(_GLYPHS[letter][row_index].replace("█", "██"), style=f"bold {color}")
        rows.append(line)
    return Group(*rows)



def show_welcome(console: Console | None = None, *, wait_for_enter: bool = True) -> None:
    """Render the FORGEX terminal welcome screen."""
    target = console or Console()
    target.clear()

    eyebrow = Text("Welcome to the FORGEX terminal coding agent!", style=f"bold {_HIGHLIGHT}")
    wordmark = _build_wordmark()
    tagline = Text("Build beyond the ordinary.", style=f"bold {_HIGHLIGHT}")
    description = Text("Plan  •  Code  •  Test  •  Improve", style=_MUTED)
    content = Group(
        Align.center(eyebrow),
        Text(""),
        Align.center(wordmark),
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
            padding=(1, 2),
            expand=False,
        )
    )
    target.print()
    prompt = Text("Press Enter to open your workspace", style=f"bold {_HIGHLIGHT}")
    target.print(Align.center(prompt))
    if wait_for_enter:
        Prompt.ask(
            f"[{_HIGHLIGHT}]Continue[/{_HIGHLIGHT}]",
            console=target,
            default="",
            show_default=False,
        )


__all__ = ["show_welcome"]
