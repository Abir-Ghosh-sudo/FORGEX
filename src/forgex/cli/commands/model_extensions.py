"""Extended model commands: `forgex model pull`, `forgex model use`."""

from __future__ import annotations

import typer
from rich.console import Console

from forgex.cli.commands.model import app as model_app
from forgex.config import get_settings
from forgex.models.manager import ModelManager

console = Console()


@model_app.command("pull")
def model_pull(
    name: str = typer.Argument(..., help="Model name to pull (e.g. qwen2.5-coder:7b)."),
) -> None:
    """Pull a model from Ollama."""
    settings = get_settings()
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


@model_app.command("use")
def model_use(
    provider: str = typer.Argument(..., help="Provider: ollama, llama_cpp, transformers."),
    model: str = typer.Argument(..., help="Model name or path."),
) -> None:
    """Set the active model provider and model."""
    settings = get_settings()
    settings.model.provider = provider
    settings.model.model_name = model
    console.print(f"[green]Model configured:[/green] provider={provider}, model={model}")
    console.print("[yellow]Note:[/yellow] Changes apply to the current session only unless saved to .env.")


@model_app.command("download")
def model_download(
    repo_id: str = typer.Argument(..., help="Hugging Face repo ID (e.g. Qwen/Qwen2.5-Coder-7B-Instruct)."),
) -> None:
    """Download model weights from Hugging Face Hub."""
    settings = get_settings()
    manager = ModelManager(settings.model)
    try:
        result = manager.download(repo_id)
        console.print(f"[green]Downloaded:[/green] {result.repo_id} -> {result.local_path}")
        if result.files:
            console.print(f"Files: {', '.join(result.files[:5])}")
    except Exception as exc:
        console.print(f"[red]Download failed:[/red] {exc}")
        raise typer.Exit(code=1)


__all__ = ["model_pull", "model_use", "model_download"]
