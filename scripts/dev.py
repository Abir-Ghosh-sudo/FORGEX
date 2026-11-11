"""FORGEX development scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"> {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def lint() -> int:
    """Run ruff linting."""
    return run(["ruff", "check", "src"]).returncode


def format_code() -> int:
    """Run ruff formatting."""
    return run(["ruff", "format", "src"]).returncode


def typecheck() -> int:
    """Run mypy type checking."""
    return run(["mypy", "src"]).returncode


def test() -> int:
    """Run pytest."""
    return run(["pytest", "tests"]).returncode


def build_native() -> int:
    """Build native C++ extension."""
    return run(["cmake", "-S", ".", "-B", "build", "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release"]).returncode or run(
        ["cmake", "--build", "build", "--config", "Release"]
    ).returncode


def clean() -> int:
    """Clean build artifacts."""
    import shutil

    for d in ("build", ".native-install", "*.egg-info", "dist"):
        for p in PROJECT_ROOT.glob(d):
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
    print("Cleaned.")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    commands = {
        "lint": lint,
        "format": format_code,
        "typecheck": typecheck,
        "test": test,
        "build-native": build_native,
        "clean": clean,
    }
    if command in commands:
        sys.exit(commands[command]())
    else:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(commands)}")
        sys.exit(1)
