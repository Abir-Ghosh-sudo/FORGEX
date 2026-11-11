"""Local model management commands for FORGEX."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from forgex.config import get_settings
from forgex.models.manager import ModelManager

app = typer.Typer(
    name="model",
    help="Inspect and manage local AI models.",
    no_args_is_help=True,
)

console = Console()


def _get_model_settings() -> Any:
    """Return the application's model settings."""
    settings = get_settings()
    return settings.model


def _run_ollama(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute an Ollama CLI command safely."""
    executable = shutil.which("ollama")

    if not executable:
        raise RuntimeError("Ollama is not installed or not available in PATH.")

    return subprocess.run(
        [executable, *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@app.command("status")
def model_status() -> None:
    """Show the currently configured model and provider."""
    try:
        settings = _get_model_settings()
    except Exception as exc:
        console.print(f"[red]Could not load model configuration:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="FORGEX Model Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Provider", str(settings.provider))
    table.add_row("Model", str(settings.model_name))
    table.add_row("Model Path", str(settings.model_path or "Not configured"))
    table.add_row("Ollama URL", str(settings.ollama_base_url))
    table.add_row("Context Tokens", str(settings.context_window))
    table.add_row("Output Tokens", str(settings.max_output_tokens))
    table.add_row("Local Files Only", str(settings.local_files_only))

    console.print(table)


@app.command("list")
def list_models() -> None:
    """List models available in the local Ollama installation."""
    try:
        result = _run_ollama(["list"])
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Unable to list models:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if result.returncode != 0:
        console.print(
            f"[red]Ollama returned an error:[/red] "
            f"{result.stderr.strip() or 'Unknown error'}"
        )
        raise typer.Exit(code=1)

    output = result.stdout.strip()

    if not output:
        console.print("[yellow]No local Ollama models found.[/yellow]")
        return

    console.print("[bold cyan]Installed Local Models[/bold cyan]")
    console.print(output)


@app.command("pull")
def model_pull(
    name: str = typer.Argument(
        ...,
        help="Model name to pull (e.g. qwen2.5-coder:7b).",
    ),
) -> None:
    """Pull a model from Ollama."""
    settings = _get_model_settings()
    manager = ModelManager(settings.model)
    try:
        success, output = manager.pull_ollama_model(name)
        if success:
            console.print(f"[green]{output}[/green]")
        else:
            console.print(f"[red]Pull failed:[/red] {output}")
            raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command("use")
def model_use(
    provider: str = typer.Argument(
        ...,
        help="Provider: ollama, llama_cpp, transformers.",
    ),
    model: str = typer.Argument(
        ...,
        help="Model name or path.",
    ),
) -> None:
    """Set the active model provider and model."""
    settings = _get_model_settings()
    settings.model.provider = provider
    settings.model.model_name = model
    console.print(f"[green]Model configured:[/green] provider={provider}, model={model}")
    console.print("[yellow]Note:[/yellow] Changes apply to the current session only unless saved to .env.")


@app.command("download")
def model_download(
    repo_id: str = typer.Argument(
        ...,
        help="Hugging Face repo ID (e.g. Qwen/Qwen2.5-Coder-7B-Instruct).",
    ),
) -> None:
    """Download model weights from Hugging Face Hub."""
    settings = _get_model_settings()
    manager = ModelManager(settings.model)
    try:
        result = manager.download(repo_id)
        console.print(f"[green]Downloaded:[/green] {result.repo_id} -> {result.local_path}")
        if result.files:
            console.print(f"Files: {', '.join(result.files[:5])}")
    except Exception as exc:
        console.print(f"[red]Download failed:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command("inspect")
def inspect_model(
    name: str = typer.Argument(
        ...,
        help="Name of the installed Ollama model.",
    ),
) -> None:
    """Inspect details of an installed local Ollama model."""
    try:
        result = _run_ollama(["show", name])
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Unable to inspect model:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if result.returncode != 0:
        console.print(
            f"[red]Model inspection failed:[/red] "
            f"{result.stderr.strip() or 'Unknown error'}"
        )
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Model: {name}[/bold cyan]")
    console.print(result.stdout.strip())


@app.command("inspect-json")
def inspect_model_json(
    name: str = typer.Argument(
        ...,
        help="Name of the installed Ollama model.",
    ),
) -> None:
    """Display structured model information when available."""
    try:
        result = _run_ollama(["show", name, "--json"])
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Unable to inspect model:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if result.returncode != 0:
        console.print(
            f"[red]Model inspection failed:[/red] "
            f"{result.stderr.strip() or 'Unknown error'}"
        )
        raise typer.Exit(code=1)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        console.print("[yellow]Ollama did not return valid JSON.[/yellow]")
        console.print(result.stdout)
        return

    console.print_json(data=data)
