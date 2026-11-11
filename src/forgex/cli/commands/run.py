"""Task execution command for FORGEX."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.status import Status

from forgex.core import ForgexApplication
from forgex.core.exceptions import ForgexError

console = Console()


def _validate_workspace(path: Path) -> Path:
    """Validate and normalize the workspace directory."""
    try:
        workspace = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise typer.BadParameter(f"Cannot resolve workspace: {exc}") from exc

    if not workspace.is_dir():
        raise typer.BadParameter(f"Workspace is not a directory: {workspace}")

    return workspace


async def _execute_task(
    workspace: Path,
    instruction: str,
) -> None:
    """Initialize FORGEX and execute a task."""
    application = ForgexApplication(workspace=workspace)

    try:
        with Status(
            "[cyan]Initializing FORGEX...[/cyan]",
            console=console,
            spinner="dots",
        ) as status:
            await application.start()
            status.update("[cyan]Preparing task execution...[/cyan]")

        with console.status(
            "[bold cyan]FORGEX is processing your task...[/bold cyan]",
            spinner="dots",
        ):
            result = await application.execute_task(instruction)

        console.print()
        console.print(
            Panel(
                "[green]Task execution completed.[/green]",
                title="FORGEX",
                border_style="green",
            )
        )

        if result is not None:
            console.print(result)

    finally:
        await application.shutdown()


def run_command(
    instruction: str = typer.Argument(
        ...,
        help="Natural-language coding task.",
    ),
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Project directory where the task should run.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
) -> None:
    """Execute an autonomous coding task in the selected workspace."""
    instruction = instruction.strip()

    if not instruction:
        raise typer.BadParameter("Task instruction cannot be empty.")

    workspace = _validate_workspace(workspace)

    console.print()
    console.print(
        Panel(
            f"[bold]{instruction}[/bold]\n\n[dim]Workspace: {workspace}[/dim]",
            title="FORGEX Task",
            border_style="cyan",
        )
    )

    try:
        asyncio.run(_execute_task(workspace, instruction))

    except KeyboardInterrupt:
        console.print("\n[yellow]Task interrupted by user.[/yellow]")
        raise typer.Exit(code=130) from None

    except ForgexError as exc:
        console.print(f"\n[red]FORGEX error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    except Exception as exc:
        console.print(f"\n[red]Unexpected execution error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
