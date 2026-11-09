"""Installation and update information commands for FORGEX."""

from __future__ import annotations

import importlib.metadata
import platform
import shutil
import subprocess
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forgex import __version__

app = typer.Typer(
    name="update",
    help="Inspect FORGEX installation and update information.",
    no_args_is_help=True,
)

console = Console()


def _get_installed_version() -> str:
    """Get the installed distribution version."""
    try:
        return importlib.metadata.version("forgex-ai")
    except importlib.metadata.PackageNotFoundError:
        return __version__


def _get_python_environment() -> str:
    """Identify the current Python environment."""
    return sys.prefix


@app.command("status")
def update_status() -> None:
    """Display installed version and environment information."""
    table = Table(title="FORGEX Installation")

    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("FORGEX Version", _get_installed_version())
    table.add_row("Package Version", __version__)
    table.add_row("Python Version", platform.python_version())
    table.add_row("Python Executable", sys.executable)
    table.add_row("Environment", _get_python_environment())
    table.add_row("Operating System", platform.platform())

    console.print(table)


@app.command("check")
def check_update() -> None:
    """Check whether a newer PyPI release is available."""
    installed = _get_installed_version()

    if not shutil.which("python"):
        console.print("[red]Python executable not found.[/red]")
        raise typer.Exit(code=1)

    console.print("[cyan]Checking package information...[/cyan]")

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "index",
                "versions",
                "forgex-ai",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            shell=False,
        )

    except subprocess.TimeoutExpired:
        console.print("[yellow]Package lookup timed out.[/yellow]")
        raise typer.Exit(code=1) from None

    except OSError as exc:
        console.print(f"[red]Unable to execute pip:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if result.returncode != 0:
        console.print(
            "[yellow]Could not retrieve package versions. "
            "Check network access and package availability.[/yellow]"
        )

        if result.stderr:
            console.print(result.stderr.strip())

        return

    console.print(
        Panel(
            f"Installed version: [bold cyan]{installed}[/bold cyan]\n\n"
            f"{result.stdout.strip()}",
            title="Package Version Information",
            border_style="cyan",
        )
    )

    console.print(
        "[dim]This command only checks package information. "
        "It does not install or modify anything.[/dim]"
    )


@app.command("environment")
def environment_info() -> None:
    """Show Python and package installation information."""
    packages = [
        "forgex-ai",
        "typer",
        "rich",
        "pydantic",
        "langchain",
        "langchain-core",
        "langgraph",
        "langchain-huggingface",
        "langchain-ollama",
        "ollama",
        "huggingface-hub",
        "pybind11",
    ]

    table = Table(title="FORGEX Environment Dependencies")
    table.add_column("Package", style="cyan")
    table.add_column("Version")
    table.add_column("Status")

    for package in packages:
        try:
            version = importlib.metadata.version(package)
            status = "[green]Installed[/green]"
        except importlib.metadata.PackageNotFoundError:
            version = "-"
            status = "[yellow]Not installed[/yellow]"

        table.add_row(package, version, status)

    console.print(table)