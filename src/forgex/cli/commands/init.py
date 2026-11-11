"""FORGEX `init` command for project initialization."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from forgex.config import get_settings
from forgex.git.manager import GitManager

app = typer.Typer(
    name="init",
    help="Initialize a FORGEX project in the current directory.",
)

console = Console()


@app.command()
def init(
    directory: str = typer.Argument(".", help="Directory to initialize."),
    git: bool = typer.Option(False, "--git", help="Initialize a Git repository."),
) -> None:
    """Initialize a FORGEX project."""
    target = Path(directory).expanduser().resolve()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        console.print(f"[red]Cannot create directory:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    settings = get_settings()
    if settings.app.workspace is None:
        settings.app.workspace = target

    created: list[str] = []
    for name in (".forgex", ".forgex/memory", ".forgex/sessions"):
        p = target / name
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(name)

    if git:
        try:
            git_manager = GitManager(target)
            result = git_manager.init_repo()
            if result.success:
                console.print("[green]Git repository initialized.[/green]")
            else:
                console.print(f"[yellow]Git init skipped:[/yellow] {result.message}")
        except Exception as exc:
            console.print(f"[yellow]Git init unavailable:[/yellow] {exc}")

    table = Table(title="FORGEX Project Initialized")
    table.add_column("Item", style="cyan")
    table.add_column("Path")
    table.add_row("Workspace", str(target))
    table.add_row("Config", str(target / ".forgex"))
    if created:
        table.add_row("Created", ", ".join(created))
    console.print(table)
    console.print("\nRun [bold]forgex chat[/bold] to start coding.")


__all__ = ["app", "init"]
