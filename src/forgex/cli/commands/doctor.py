"""Environment and hardware diagnostics command for FORGEX."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from dataclasses import dataclass

import typer
from rich.console import Console
from rich.table import Table

from forgex.utils.system import get_hardware_info, get_system_info


console = Console()


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    name: str
    status: str
    details: str


def _check_python() -> DiagnosticResult:
    version = sys.version_info
    supported = version >= (3, 11)

    return DiagnosticResult(
        name="Python",
        status="PASS" if supported else "FAIL",
        details=f"{version.major}.{version.minor}.{version.micro}",
    )


def _check_ollama() -> DiagnosticResult:
    executable = shutil.which("ollama")

    if executable:
        return DiagnosticResult(
            name="Ollama",
            status="PASS",
            details=executable,
        )

    return DiagnosticResult(
        name="Ollama",
        status="INFO",
        details="Not installed or not available in PATH",
    )


def _check_native_engine() -> DiagnosticResult:
    try:
        available = importlib.util.find_spec("forgex.engine._native")
    except (ImportError, ModuleNotFoundError, ValueError):
        available = None

    if available is not None:
        return DiagnosticResult(
            name="Native Engine",
            status="PASS",
            details="C++ extension detected",
        )

    return DiagnosticResult(
        name="Native Engine",
        status="INFO",
        details="C++ extension unavailable; Python fallback expected",
    )


def _check_git() -> DiagnosticResult:
    executable = shutil.which("git")

    if executable:
        return DiagnosticResult(
            name="Git",
            status="PASS",
            details=executable,
        )

    return DiagnosticResult(
        name="Git",
        status="WARN",
        details="Git executable not found in PATH",
    )


def collect_diagnostics() -> list[DiagnosticResult]:
    """Collect local environment diagnostics without modifying the system."""
    return [
        _check_python(),
        _check_ollama(),
        _check_native_engine(),
        _check_git(),
    ]


def doctor_command(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show additional system and hardware information.",
    ),
) -> None:
    """Check whether the local environment is ready to run FORGEX."""
    try:
        system = get_system_info()
        hardware = get_hardware_info()
        results = collect_diagnostics()
    except Exception as exc:
        console.print(f"[red]Diagnostics failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print()
    console.print("[bold cyan]FORGEX System Diagnostics[/bold cyan]")
    console.print("[dim]Build Beyond Code.[/dim]")
    console.print()

    table = Table(title="Environment Checks", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details", overflow="fold")

    status_styles = {
        "PASS": "[green]PASS[/green]",
        "WARN": "[yellow]WARN[/yellow]",
        "FAIL": "[red]FAIL[/red]",
        "INFO": "[dim]INFO[/dim]",
    }

    for result in results:
        table.add_row(
            result.name,
            status_styles.get(result.status, result.status),
            result.details,
        )

    console.print(table)

    if verbose:
        console.print()
        console.print("[bold]System Information[/bold]")

        system_table = Table(show_header=False)
        system_table.add_column("Property", style="cyan")
        system_table.add_column("Value")

        system_table.add_row("Operating System", system.platform)
        system_table.add_row("Architecture", system.architecture)
        system_table.add_row("Processor", system.processor or "Unknown")
        system_table.add_row("CPU Cores", str(hardware.cpu_cores))
        system_table.add_row("Total RAM", f"{hardware.total_ram_gb:.2f} GB")
        system_table.add_row("Available RAM", f"{hardware.available_ram_gb:.2f} GB")
        system_table.add_row("GPU", hardware.gpu_name or "Not detected")

        console.print(system_table)

    failures = [item for item in results if item.status == "FAIL"]
    warnings = [item for item in results if item.status == "WARN"]

    console.print()

    if failures:
        console.print("[red]Some required checks failed.[/red]")
        raise typer.Exit(code=1)

    if warnings:
        console.print("[yellow]Diagnostics completed with warnings.[/yellow]")
    else:
        console.print("[green]Diagnostics completed.[/green]")