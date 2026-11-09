"""Session management commands for FORGEX."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from forgex.config import get_settings

app = typer.Typer(
    name="session",
    help="Inspect and manage FORGEX sessions.",
    no_args_is_help=True,
)

console = Console()


def _get_session_store() -> Any:
    """Retrieve the session repository registered in the application."""
    from forgex.sessions import SessionManager

    settings = get_settings()
    manager = SessionManager(storage_path=Path(settings.storage.data_dir))
    return manager


def _format_datetime(value: Any) -> str:
    """Format session timestamps for terminal display."""
    if value is None:
        return "Unknown"

    if isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    return str(value)


@app.command("list")
def list_sessions(
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        min=1,
        max=200,
        help="Maximum number of sessions to display.",
    ),
) -> None:
    """List stored FORGEX sessions."""
    try:
        manager = _get_session_store()
        sessions = manager.list_sessions(limit=limit)

        if not sessions:
            console.print("[yellow]No sessions found.[/yellow]")
            return

        table = Table(title="FORGEX Sessions")
        table.add_column("Session ID", style="cyan")
        table.add_column("Workspace")
        table.add_column("Status")
        table.add_column("Created")

        for session in sessions:
            table.add_row(
                str(session.id),
                str(session.workspace),
                str(session.status),
                _format_datetime(session.created_at),
            )

        console.print(table)

    except Exception as exc:
        console.print(f"[red]Unable to list sessions:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("show")
def show_session(
    session_id: str = typer.Argument(
        ...,
        help="Session identifier.",
    ),
) -> None:
    """Display details of a stored session."""
    try:
        manager = _get_session_store()
        session = manager.get_session(session_id)

        if session is None:
            console.print(f"[yellow]Session not found: {session_id}[/yellow]")
            raise typer.Exit(code=1)

        details = {
            "id": str(session.id),
            "workspace": str(session.workspace),
            "status": str(session.status),
            "created_at": _format_datetime(session.created_at),
            "updated_at": _format_datetime(
                getattr(session, "updated_at", None)
            ),
            "metadata": getattr(session, "metadata", {}),
        }

        console.print_json(data=details)

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Unable to inspect session:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("delete")
def delete_session(
    session_id: str = typer.Argument(
        ...,
        help="Session identifier to delete.",
    ),
    force: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Delete without confirmation.",
    ),
) -> None:
    """Delete a stored session."""
    if not force:
        confirmed = typer.confirm(
            f"Delete session '{session_id}'?",
            default=False,
        )

        if not confirmed:
            console.print("[yellow]Deletion cancelled.[/yellow]")
            raise typer.Exit()

    try:
        manager = _get_session_store()
        deleted = manager.delete_session(session_id)

        if not deleted:
            console.print(f"[yellow]Session not found: {session_id}[/yellow]")
            raise typer.Exit(code=1)

        console.print(
            f"[green]Session deleted:[/green] {session_id}"
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Session deletion failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc