"""Unit tests for FORGEX CLI."""

from __future__ import annotations

from typer.testing import CliRunner
from forgex.cli.app import app


class TestCLI:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "FORGEX" in result.output

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "forgex" in result.output.lower()


def test_welcome_screen_renders_forgex_branding():
    from rich.console import Console

    from forgex.cli.welcome import show_welcome

    console = Console(record=True, width=120)
    show_welcome(console, wait_for_enter=False)
    output = console.export_text()

    assert "Welcome to the FORGEX terminal coding agent!" in output
    assert "Build Beyond Code." in output
    assert "Press Enter to continue" not in output
