#!/usr/bin/env python3
"""Build a portable ZIP with SKILL.md at the archive root."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = SKILL_ROOT / "dist" / "forgex-terminal-coding-skill.zip"


def build_archive(output: Path) -> Path:
    skill_file = SKILL_ROOT / "SKILL.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"Missing required skill entrypoint: {skill_file}")

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(
        path
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
        and "dist" not in path.relative_to(SKILL_ROOT).parts
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(SKILL_ROOT))

    with ZipFile(output, "r") as archive:
        names = archive.namelist()
        if "SKILL.md" not in names:
            raise RuntimeError("Archive validation failed: SKILL.md is not at the root.")
        if archive.testzip() is not None:
            raise RuntimeError("Archive validation failed: a ZIP member is corrupt.")

    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output ZIP path (default: package dist directory).",
    )
    args = parser.parse_args()

    archive = build_archive(args.output)
    print(f"Created skill package: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
