"""Project testing commands for FORGEX."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="test",
    help="Run and inspect project tests.",
    no_args_is_help=True,
)

console = Console()


def _find_test_runner(workspace: Path) -> str:
    """Detect an available Python test runner."""
    if (workspace / "pytest.ini").is_file():
        return "pytest"

    if (workspace / "pyproject.toml").is_file():
        try:
            content = (workspace / "pyproject.toml").read_text(encoding="utf-8")
            if "[tool.pytest.ini_options]" in content:
                return "pytest"
        except OSError:
            pass

    if shutil.which("pytest"):
        return "pytest"

    return "unavailable"


def _run_process(
    command: list[str],
    workspace: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Run a test process and capture its output."""
    return subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )


@app.command("run")
def run_tests(
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Project directory.",
    ),
    target: str = typer.Argument(
        ".",
        help="Test file, directory, or test selector.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Display verbose test output.",
    ),
    timeout: int = typer.Option(
        600,
        "--timeout",
        min=1,
        max=3600,
        help="Maximum test execution time in seconds.",
    ),
) -> None:
    """Execute the project's Python test suite."""
    workspace = workspace.expanduser().resolve()

    if not workspace.is_dir():
        raise typer.BadParameter("Workspace must be a directory.")

    runner = _find_test_runner(workspace)

    if runner == "unavailable":
        console.print("[red]pytest is not installed or available in PATH.[/red]")
        raise typer.Exit(code=1)

    command = ["pytest", target]

    if verbose:
        command.append("-v")

    command.extend(["--color=no"])

    console.print(
        Panel(
            f"[bold cyan]Test Execution[/bold cyan]\n"
            f"Workspace: {workspace}\n"
            f"Target: {target}\n"
            f"Timeout: {timeout}s",
            border_style="cyan",
        )
    )

    try:
        result = _run_process(command, workspace, timeout)

    except subprocess.TimeoutExpired:
        console.print(f"[red]Tests exceeded the {timeout}-second timeout.[/red]")
        raise typer.Exit(code=124) from None

    except OSError as exc:
        console.print(f"[red]Could not start tests:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    output = result.stdout.strip()
    errors = result.stderr.strip()

    if output:
        console.print(output)

    if errors:
        console.print(f"[yellow]{errors}[/yellow]")

    table = Table(title="Test Result")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Exit Code", str(result.returncode))
    table.add_row(
        "Status",
        "[green]PASSED[/green]" if result.returncode == 0 else "[red]FAILED[/red]",
    )
    table.add_row("Runner", "pytest")

    console.print(table)

    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@app.command("discover")
def discover_tests(
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Project directory.",
    ),
) -> None:
    """Discover common Python test files."""
    workspace = workspace.expanduser().resolve()

    if not workspace.is_dir():
        raise typer.BadParameter("Workspace must be a directory.")

    ignored = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "build",
        "dist",
    }

    discovered: list[Path] = []

    for current_root, directories, filenames in __import__("os").walk(workspace):
        directories[:] = [
            directory
            for directory in directories
            if directory not in ignored and not (Path(current_root) / directory).is_symlink()
        ]

        for filename in filenames:
            if filename.startswith("test_") or filename.endswith("_test.py"):
                discovered.append(Path(current_root) / filename)

    table = Table(title="Discovered Python Tests")
    table.add_column("Test File", style="cyan")

    for path in sorted(discovered):
        table.add_row(path.relative_to(workspace).as_posix())

    if not discovered:
        console.print("[yellow]No Python test files found.[/yellow]")
        return

    console.print(table)
    console.print(f"\n[green]Found {len(discovered)} test files.[/green]")
