"""Context assembly: builds bounded prompt context from repository snapshot."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from forgex.context.file_retrieval import FileRetriever

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Assembles task-scoped context text within a token budget."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.retriever = FileRetriever(self.workspace)

    def assemble(
        self,
        *,
        task: str,
        focus_files: list[str] | None = None,
        symbols: dict[str, list[dict[str, Any]]] | None = None,
        max_tokens: int = 16384,
    ) -> str:
        """Build a bounded context text for model prompts."""
        parts: list[str] = []
        budget = max(512, max_tokens)
        used = 0

        header = f"## Repository Context\nTask: {task}\nWorkspace: {self.workspace}\n"
        parts.append(header)
        used += self._estimate_tokens(header)

        focus_files = focus_files or []
        included: set[str] = set()

        # Include symbol summary first
        if symbols:
            sym_text = self._format_symbols(symbols)
            if sym_text:
                cost = self._estimate_tokens(sym_text)
                if used + cost <= budget:
                    parts.append(sym_text)
                    used += cost

        # Include focused file contents
        for rel in focus_files:
            if rel in included:
                continue
            full = self.workspace / rel
            if not full.exists() or not full.is_file():
                continue
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            file_block = f"\n### File: {rel}\n```\n{text}\n```\n"
            cost = self._estimate_tokens(file_block)
            if used + cost <= budget:
                parts.append(file_block)
                used += cost
                included.add(rel)
            else:
                remaining = budget - used
                if remaining > 200:
                    truncated = text[: max(0, int(remaining * 4))]
                    parts.append(f"\n### File: {rel} (truncated)\n```\n{truncated}\n```\n")
                break

        result = "\n".join(parts)
        logger.debug(
            "Context assembled: %d chars, ~%d tokens, %d files",
            len(result),
            used,
            len(included),
        )
        return result

    @staticmethod
    def _format_symbols(symbols: dict[str, list[dict[str, Any]]]) -> str:
        lines = ["## Symbols"]
        count = 0
        for file_path, file_symbols in sorted(symbols.items()):
            names = [s.get("name", "") for s in file_symbols[:10]]
            if names:
                lines.append(f"- {file_path}: {', '.join(names)}")
                count += len(names)
            if count >= 200:
                break
        return "\n".join(lines) if count else ""

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)


__all__ = ["ContextAssembler"]
