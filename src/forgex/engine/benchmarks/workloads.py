"""Standard benchmark workloads for the FORGEX native engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runner import BenchmarkRunner


class EngineBenchmarks:
    """Benchmark native engine components when available."""

    def __init__(self, runner: BenchmarkRunner | None = None) -> None:
        self.runner = runner or BenchmarkRunner()

    def run_core(self, engine: Any) -> None:
        text = ("FORGEX autonomous coding engine build beyond code\n") * 100

        self.runner.run(
            "core.normalize_whitespace",
            lambda: engine.normalize_whitespace(text),
            metadata={"input_characters": len(text)},
        )

        self.runner.run(
            "core.analyze_text",
            lambda: engine.analyze_text(text),
            metadata={"input_characters": len(text)},
        )

        self.runner.run(
            "core.hash_string",
            lambda: engine.hash_string(text),
            metadata={"input_characters": len(text)},
        )

        self.runner.run(
            "core.to_lower",
            lambda: engine.to_lower(text),
            metadata={"input_characters": len(text)},
        )

    def run_parser(self, parser: Any) -> None:
        source = (
            """
def calculate_total(items):
    total = 0
    for item in items:
        total += item
    return total

class Calculator:
    def add(self, first, second):
        return first + second
"""
            * 20
        )

        self.runner.run(
            "parser.tokenize",
            lambda: parser.tokenize(source, "python"),
            metadata={"input_characters": len(source)},
        )

        self.runner.run(
            "parser.parse",
            lambda: parser.parse(source, "python"),
            metadata={"input_characters": len(source)},
        )

    def run_search(self, search_engine: Any) -> None:
        content = ("def forgex_engine():\n    return 'Build Beyond Code'\n\n") * 500

        self.runner.run(
            "search.text",
            lambda: search_engine.search_text(
                content,
                "forgex_engine",
            ),
            metadata={"input_characters": len(content)},
        )

        self.runner.run(
            "search.regex",
            lambda: search_engine.search_regex(
                content,
                r"def\s+\w+",
            ),
            metadata={"input_characters": len(content)},
        )

    def run_indexing(
        self,
        indexer: Any,
        workspace: str | Path,
    ) -> None:
        root = Path(workspace).resolve()

        self.runner.run(
            "indexing.directory",
            lambda: indexer.index_directory(root),
            iterations=1,
            metadata={"workspace": str(root)},
        )

    def run_all(
        self,
        *,
        core: Any | None = None,
        parser: Any | None = None,
        search: Any | None = None,
        indexer: Any | None = None,
        workspace: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run benchmarks for available components."""

        if core is not None:
            self.run_core(core)

        if parser is not None:
            self.run_parser(parser)

        if search is not None:
            self.run_search(search)

        if indexer is not None and workspace is not None:
            self.run_indexing(indexer, workspace)

        return self.runner.create_report().to_dict()
