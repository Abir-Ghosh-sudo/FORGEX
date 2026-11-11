"""Interactive terminal chat for FORGEX."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status

from forgex.core import ForgexApplication
from forgex.core.exceptions import ForgexError

console = Console()

EXIT_COMMANDS = {"/exit", "/quit", "/q"}
HELP_COMMANDS = {"/help", "/h"}
CLEAR_COMMANDS = {"/clear"}


def _show_welcome(workspace: Path) -> None:
    """Display the interactive session welcome screen."""
    console.print()

    console.print(
        Panel(
            "[bold cyan]FORGEX Interactive Session[/bold cyan]\n"
            "[dim]Build Beyond Code.[/dim]\n\n"
            f"[bold]Workspace:[/bold] {workspace}\n\n"
            "[green]/help[/green]  Show available commands\n"
            "[green]/clear[/green] Clear terminal screen\n"
            "[green]/exit[/green]  End the session",
            title="FORGEX",
            border_style="cyan",
        )
    )


def _show_help() -> None:
    """Display interactive command help."""
    console.print(
        Panel(
            "[bold]Available commands[/bold]\n\n"
            "[cyan]/help[/cyan]   Show this help message\n"
            "[cyan]/clear[/cyan]  Clear the terminal\n"
            "[cyan]/exit[/cyan]   Exit the session\n\n"
            "[dim]Any other input is treated as a coding task.[/dim]",
            title="Help",
            border_style="blue",
        )
    )


async def _interactive_session(workspace: Path) -> None:
    """Run a persistent FORGEX application session."""
    application = ForgexApplication(workspace=workspace)

    try:
        await application.start()
        _show_welcome(workspace)

        while True:
            try:
                instruction = Prompt.ask("\n[bold cyan]forgex[/bold cyan]").strip()

            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Ending session...[/yellow]")
                break

            if not instruction:
                continue

            command = instruction.lower()

            if command in EXIT_COMMANDS:
                console.print("[dim]Goodbye![/dim]")
                break

            if command in HELP_COMMANDS:
                _show_help()
                continue

            if command in CLEAR_COMMANDS:
                console.clear()
                continue

            console.print()

            try:
                with Status(
                    "[cyan]FORGEX is working...[/cyan]",
                    console=console,
                    spinner="dots",
                ):
                    result = await application.execute_task(instruction)

                console.print(
                    Panel(
                        "[green]Task execution finished.[/green]",
                        title="FORGEX",
                        border_style="green",
                    )
                )

                if result is not None:
                    console.print(result)

            except ForgexError as exc:
                console.print(f"[red]FORGEX error:[/red] {exc}")

            except Exception as exc:
                console.print(f"[red]Task failed:[/red] {type(exc).__name__}: {exc}")

    finally:
        await application.shutdown()


def chat_command(
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Project directory for this session.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
) -> None:
    """Start an interactive FORGEX coding session."""
    try:
        workspace = workspace.expanduser().resolve(strict=True)

        if not workspace.is_dir():
            raise typer.BadParameter("Workspace must be a directory.")

        asyncio.run(_interactive_session(workspace))

    except KeyboardInterrupt:
        console.print("\n[yellow]Session interrupted.[/yellow]")
        raise typer.Exit(code=130) from None

    except ForgexError as exc:
        console.print(f"[red]FORGEX initialization failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    except typer.BadParameter:
        raise

    except Exception as exc:
        console.print(f"[red]Unable to start chat:[/red] {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1) from exc
