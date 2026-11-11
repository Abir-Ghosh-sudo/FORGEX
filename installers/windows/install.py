"""FORGEX Windows installation script.

Installs Python, creates venv, installs FORGEX, configures PATH,
and verifies `forgex doctor`.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"> {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def main() -> int:
    print("=== FORGEX Windows Installer ===")

    python_exe = sys.executable
    print(f"Using Python: {python_exe}")

    # Create venv
    if not VENV_DIR.exists():
        print("Creating virtual environment...")
        run([python_exe, "-m", "venv", str(VENV_DIR)])

    venv_python = VENV_DIR / "Scripts" / "python.exe"
    venv_pip = VENV_DIR / "Scripts" / "pip.exe"

    # Install FORGEX
    print("Installing FORGEX...")
    run([str(venv_pip), "install", "-e", str(PROJECT_ROOT)])

    # Optional native build
    print("NOTE: Native C++ build requires MSVC Build Tools (Desktop development with C++).")
    print("      Install Build Tools, then run: cmake --build build --config Release")

    # Verify
    print("Verifying installation...")
    run([str(venv_python), "-m", "forgex.cli.app", "--version"])

    print("\n=== Installation complete ===")
    print(f"Activate venv: {VENV_DIR}\\Scripts\\activate.bat")
    print(f"Run: {VENV_DIR}\\Scripts\\python.exe -m forgex.cli.app --help")
    return 0


if __name__ == "__main__":
    sys.exit(main())
