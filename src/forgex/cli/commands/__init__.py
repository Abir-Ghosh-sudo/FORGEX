"""Built-in command modules for the FORGEX CLI."""

from forgex.cli.commands.analyze import (
    analyze_command,
    analyze_workspace,
)
from forgex.cli.commands.chat import chat_command
from forgex.cli.commands.config import app as config_app
from forgex.cli.commands.doctor import (
    collect_diagnostics,
    doctor_command,
)
from forgex.cli.commands.git import app as git_app
from forgex.cli.commands.init import app as init_app
from forgex.cli.commands.model import app as model_app
from forgex.cli.commands.run import run_command
from forgex.cli.commands.session import app as session_app
from forgex.cli.commands.test import app as test_app
from forgex.cli.commands.update import app as update_app

__all__ = [
    "analyze_command",
    "analyze_workspace",
    "chat_command",
    "config_app",
    "collect_diagnostics",
    "doctor_command",
    "git_app",
    "init_app",
    "model_app",
    "run_command",
    "session_app",
    "test_app",
    "update_app",
]