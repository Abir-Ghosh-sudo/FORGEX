"""Main command-line application for FORGEX."""

import typer

from forgex import __version__

app = typer.Typer(
    name="forgex",
    help="FORGEX — Build Beyond Code. Your autonomous AI coding agent.",
    no_args_is_help=True,
    add_completion=True,
)


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

    if version:
        typer.echo(f"FORGEX v{__version__}")
        raise typer.Exit()


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()