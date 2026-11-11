"""FORGEX cleanup script."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    patterns = ["build", ".native-install", "*.egg-info", "dist", "__pycache__", ".pytest_cache", ".mypy_cache"]
    cleaned = 0
    for pattern in patterns:
        for p in PROJECT_ROOT.rglob(pattern):
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                cleaned += 1
            except Exception as exc:
                print(f"Skipped {p}: {exc}")
    print(f"Cleaned {cleaned} items.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
