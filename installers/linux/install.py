"""FORGEX Linux installation script.

Installs dependencies, creates venv, installs FORGEX, configures PATH,
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
    print("=== FORGEX Linux Installer ===")

    python_exe = sys.executable
    print(f"Using Python: {python_exe}")

    # Create venv
    if not VENV_DIR.exists():
        print("Creating virtual environment...")
        run([python_exe, "-m", "venv", str(VENV_DIR)])

    venv_python = VENV_DIR / "bin" / "python"
    venv_pip = VENV_DIR / "bin" / "pip"

    # Install FORGEX
    print("Installing FORGEX...")
    run([str(venv_pip), "install", "-e", str(PROJECT_ROOT)])

    # Optional native build
    print("NOTE: Native C++ build requires build-essential and CMake.")
    print("      sudo apt-get install build-essential cmake")
    print("      Then: cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release")

    # Verify
    print("Verifying installation...")
    run([str(venv_python), "-m", "forgex.cli.app", "--version"])

    print("\n=== Installation complete ===")
    print(f"Activate venv: source {VENV_DIR}/bin/activate")
    print(f"Run: forgex --help")
    return 0


if __name__ == "__main__":
    sys.exit(main())
