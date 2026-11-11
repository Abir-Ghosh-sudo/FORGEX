"""Symbol retrieval for FORGEX context engine.

Scans source files for function/class/import symbols using lightweight
regex-based parsing, falling back to tree-sitter where available.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SymbolRetriever:
    """Extracts symbols from source files within the workspace."""

    EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".cpp", ".c", ".h", ".rs", ".go", ".java", ".rb"}

    PY_SYMBOL_RE = re.compile(
        r"(?:^\s*(?:def|class|async\s+def)\s+([A-Za-z_][A-Za-z0-9_]*))"
    )
    IMPORT_RE = re.compile(r"(?:^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*))")

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self._tree_sitter_available = self._check_tree_sitter()

    def _check_tree_sitter(self) -> bool:
        try:
            import tree_sitter  # noqa: F401
            import tree_sitter_language_pack  # noqa: F401
            return True
        except Exception:
            return False

    def scan_symbols(self) -> dict[str, list[dict[str, Any]]]:
        """Scan all supported source files for symbols."""
        symbols: dict[str, list[dict[str, Any]]] = {}
        try:
            files = [p for p in self.workspace.rglob("*") if p.is_file() and p.suffix.lower() in self.EXTENSIONS]
        except Exception:
            return symbols
        for p in files:
            rel = str(p.relative_to(self.workspace))
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                file_symbols = self._extract_symbols(text, p.suffix.lower())
                if file_symbols:
                    symbols[rel] = file_symbols
            except Exception:
                logger.debug("Symbol scan failed for %s", rel, exc_info=True)
        return symbols

    def _extract_symbols(self, text: str, ext: str) -> list[dict[str, Any]]:
        symbols: list[dict[str, Any]] = []
        if ext == ".py":
            for match in self.PY_SYMBOL_RE.finditer(text):
                symbols.append({"kind": "def_or_class", "name": match.group(1)})
            for match in self.IMPORT_RE.finditer(text):
                symbols.append({"kind": "import", "name": match.group(1)})
        else:
            # Generic line-based fallback
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith(("def ", "class ", "function ", "fn ")):
                    name_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)", stripped)
                    if name_match:
                        symbols.append({"kind": "declaration", "name": name_match.group(1)})
        return symbols[:100]

    def search_symbol(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search symbols by name substring."""
        all_symbols = self.scan_symbols()
        matches: list[dict[str, Any]] = []
        q = query.lower()
        for file_path, file_symbols in all_symbols.items():
            for sym in file_symbols:
                if q in sym.get("name", "").lower():
                    matches.append({"file": file_path, **sym})
                    if len(matches) >= limit:
                        return matches
        return matches


__all__ = ["SymbolRetriever"]
