"""Configuration management commands for FORGEX."""

from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from forgex.config import (
    ConfigurationManager,
    ForgexSettings,
    clear_settings_cache,
    get_settings,
)

app = typer.Typer(
    name="config",
    help="Inspect and manage FORGEX configuration.",
    no_args_is_help=True,
)

console = Console()


def _manager() -> ConfigurationManager:
    """Create a configuration manager."""
    return ConfigurationManager()


def _redact_secrets(value: Any, key: str = "") -> Any:
    """Redact potentially sensitive configuration values."""
    sensitive_markers = (
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "credential",
    )

    if any(marker in key.lower() for marker in sensitive_markers):
        return "***REDACTED***" if value else value

    if isinstance(value, dict):
        return {
            item_key: _redact_secrets(item_value, str(item_key))
            for item_key, item_value in value.items()
        }

    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]

    return value


def _settings_dict() -> dict[str, Any]:
    """Return current settings as a dictionary."""
    settings = get_settings()
    return settings.model_dump(mode="json")


@app.command("show")
def show_config(
    section: str | None = typer.Option(
        None,
        "--section",
        "-s",
        help="Show only one configuration section.",
    ),
    reveal_secrets: bool = typer.Option(
        False,
        "--show-secrets",
        help="Display sensitive values. Use cautiously.",
    ),
) -> None:
    """Display current FORGEX configuration."""
    try:
        data = _settings_dict()

        if section:
            if section not in data:
                raise typer.BadParameter(f"Unknown configuration section: {section}")

            data = {section: data[section]}

        if not reveal_secrets:
            data = _redact_secrets(data)

        rendered = json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )

        console.print(
            Panel(
                Syntax(rendered, "json", theme="monokai"),
                title="FORGEX Configuration",
                border_style="cyan",
            )
        )

    except typer.BadParameter:
        raise
    except Exception as exc:
        console.print(f"[red]Unable to read configuration:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("validate")
def validate_config() -> None:
    """Validate the current configuration."""
    try:
        settings = ForgexSettings()
        settings.model_dump(mode="json")

        console.print(
            Panel(
                "[green]Configuration validation successful.[/green]",
                title="FORGEX",
                border_style="green",
            )
        )

    except Exception as exc:
        console.print(f"[red]Configuration validation failed:[/red]\n{exc}")
        raise typer.Exit(code=1) from exc


@app.command("path")
def config_path() -> None:
    """Display the configuration file location."""
    try:
        manager = _manager()
        path = manager.config_path

        console.print(
            Panel(
                str(path),
                title="Configuration File",
                border_style="cyan",
            )
        )

        console.print(
            "[green]File exists.[/green]"
            if path.exists()
            else "[yellow]Configuration file has not been created yet.[/yellow]"
        )

    except Exception as exc:
        console.print(f"[red]Unable to resolve configuration path:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("reset")
def reset_config(
    force: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Reset without asking for confirmation.",
    ),
) -> None:
    """Reset saved configuration to application defaults."""
    manager = _manager()

    if not force:
        confirmed = typer.confirm(
            "Reset saved FORGEX configuration? This may overwrite custom settings.",
            default=False,
        )

        if not confirmed:
            console.print("[yellow]Reset cancelled.[/yellow]")
            raise typer.Exit()

    try:
        manager.reset()
        clear_settings_cache()

        console.print("[green]Saved configuration reset successfully.[/green]")

    except Exception as exc:
        console.print(f"[red]Configuration reset failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("sections")
def config_sections() -> None:
    """List available configuration sections."""
    try:
        data = _settings_dict()

        table = Table(title="Configuration Sections")
        table.add_column("Section", style="cyan")
        table.add_column("Fields", justify="right")

        for section, values in data.items():
            count = len(values) if isinstance(values, dict) else 1
            table.add_row(section, str(count))

        console.print(table)

    except Exception as exc:
        console.print(f"[red]Unable to list sections:[/red] {exc}")
        raise typer.Exit(code=1) from exc
