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
