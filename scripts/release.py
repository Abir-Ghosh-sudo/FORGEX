"""FORGEX release build script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"> {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def main() -> int:
    print("=== FORGEX Release Build ===")

    # Build wheel
    print("Building wheel...")
    run([sys.executable, "-m", "build", "--wheel", str(PROJECT_ROOT)])

    # Build native extension (optional)
    print("Building native C++ extension...")
    try:
        run(["cmake", "-S", ".", "-B", "build", "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release"])
        run(["cmake", "--build", "build", "--config", "Release"])
    except Exception as exc:
        print(f"Native build skipped: {exc}")

    print("=== Release build complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
