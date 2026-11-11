"""Updated CLI app integrating all modules."""

from __future__ import annotations

import typer

from forgex import __version__
from forgex.cli.commands import (
    analyze_workspace,
    chat_command,
    config_app,
    doctor_command,
    git_app,
    init_app,
    model_app,
    run_command,
    session_app,
    test_app,
    update_app,
)
from forgex.cli.slash_commands.extensions import register_extended_slash_commands

app = typer.Typer(
    name="forgex",
    help="FORGEX - Build Beyond Code. Your autonomous AI coding agent.",
    no_args_is_help=True,
    add_completion=True,
    invoke_without_command=True,
)

app.add_typer(config_app, name="config", help="Manage FORGEX configuration.")
app.add_typer(git_app, name="git", help="Manage Git operations.")
app.add_typer(model_app, name="model", help="Manage local AI models.")
app.add_typer(init_app, name="init", help="Initialize a FORGEX project.")
app.add_typer(session_app, name="session", help="Manage coding sessions.")
app.add_typer(test_app, name="test", help="Run and discover project tests.")
app.add_typer(update_app, name="update", help="Check FORGEX updates.")

app.command("doctor")(doctor_command)
app.command("analyze")(analyze_workspace)
app.command("run")(run_command)
app.command("chat")(chat_command)


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Display the FORGEX version and exit.",
        is_eager=True,
    ),
) -> None:
    """Initialize the FORGEX command-line interface."""
    register_extended_slash_commands()
    if version:
        typer.echo(f"FORGEX v{__version__}")
        raise typer.Exit()


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
