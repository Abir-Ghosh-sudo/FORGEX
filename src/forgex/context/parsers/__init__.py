"""Language parsers for context engine.

Provides lightweight language detection and parsing stubs. Tree-sitter
integration is available through existing engine components when installed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".cs": "csharp",
    ".php": "php",
}


def detect_language(file_path: str | Path) -> str | None:
    """Detect programming language from file extension."""
    path = Path(file_path)
    return LANGUAGE_MAP.get(path.suffix.lower())


def list_supported_languages() -> list[str]:
    """Return sorted list of supported language names."""
    return sorted(set(LANGUAGE_MAP.values()))


def parse_file(file_path: str | Path) -> dict[str, Any]:
    """Parse a source file into a normalized structure."""
    path = Path(file_path)
    language = detect_language(path)
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise FileNotFoundError(f"Cannot parse {path}: {exc}") from exc
    return {
        "path": str(path),
        "language": language,
        "content": content,
        "lines": content.splitlines(),
        "line_count": len(content.splitlines()),
    }


__all__ = ["detect_language", "list_supported_languages", "parse_file"]
