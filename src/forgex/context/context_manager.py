"""Context manager: repository scanning and task-specific context gathering."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from forgex.context.file_retrieval import FileRetriever
from forgex.context.context_assembler import ContextAssembler

logger = logging.getLogger(__name__)


class ContextSnapshot:
    """Normalized snapshot of repository state relevant to a task."""

    def __init__(
        self,
        workspace: Path,
        root_files: list[str],
        file_tree: dict[str, Any],
        detected_languages: list[str],
        project_type: str,
        entry_points: list[str],
        dependencies: list[str],
        imports: dict[str, list[str]],
        symbols: dict[str, list[dict[str, Any]]],
        context_text: str,
        token_estimate: int,
    ) -> None:
        self.workspace = workspace
        self.root_files = root_files
        self.file_tree = file_tree
        self.detected_languages = detected_languages
        self.project_type = project_type
        self.entry_points = entry_points
        self.dependencies = dependencies
        self.imports = imports
        self.symbols = symbols
        self.context_text = context_text
        self.token_estimate = token_estimate

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "root_files": self.root_files,
            "detected_languages": self.detected_languages,
            "project_type": self.project_type,
            "entry_points": self.entry_points,
            "dependencies": self.dependencies,
            "imports": self.imports,
            "symbol_count": sum(len(v) for v in self.symbols.values()),
            "context_text": self.context_text,
            "token_estimate": self.token_estimate,
        }


class ContextManager:
    """Scans a repository and assembles task-scoped context."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        if not self.workspace.exists():
            raise FileNotFoundError(f"Workspace does not exist: {self.workspace}")
        if not self.workspace.is_dir():
            raise NotADirectoryError(f"Workspace is not a directory: {self.workspace}")
        self.retriever = FileRetriever(self.workspace)
        self.symbols = SymbolRetriever(self.workspace)
        self.assembler = ContextAssembler(self.workspace)

    def gather_context(
        self,
        *,
        task: str,
        focus_files: list[str] | None = None,
        max_context_tokens: int = 16384,
    ) -> ContextSnapshot:
        """Build a bounded context snapshot for a coding task."""
        root_files = self._detect_root_files()
        detected_languages = self._detect_languages()
        project_type = self._detect_project_type(root_files, detected_languages)
        entry_points = self._detect_entry_points(project_type)
        dependencies = self._detect_dependencies(project_type)
        imports = self._collect_imports()
        symbols = self.symbols.scan_symbols()
        file_tree = self.retriever.build_tree(max_depth=3)
        context_text = self.assembler.assemble(
            task=task,
            focus_files=focus_files,
            symbols=symbols,
            max_tokens=max_context_tokens,
        )
        token_estimate = self._estimate_tokens(context_text)

        return ContextSnapshot(
            workspace=self.workspace,
            root_files=root_files,
            file_tree=file_tree,
            detected_languages=detected_languages,
            project_type=project_type,
            entry_points=entry_points,
            dependencies=dependencies,
            imports=imports,
            symbols=symbols,
            context_text=context_text,
            token_estimate=token_estimate,
        )

    def _detect_root_files(self) -> list[str]:
        return sorted(
            p.name
            for p in self.workspace.iterdir()
            if p.is_file() and not p.name.startswith(".")
        )[:50]

    def _detect_languages(self) -> list[str]:
        extensions: dict[str, str] = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript React",
            ".jsx": "JavaScript React",
            ".cpp": "C++",
            ".c": "C",
            ".h": "C/C++ Header",
            ".rs": "Rust",
            ".go": "Go",
            ".java": "Java",
            ".rb": "Ruby",
            ".cs": "C#",
            ".php": "PHP",
        }
        found: set[str] = set()
        for p in self.workspace.rglob("*"):
            if p.is_file() and p.suffix.lower() in extensions:
                found.add(extensions[p.suffix.lower()])
        return sorted(found)

    def _detect_project_type(
        self,
        root_files: list[str],
        detected_languages: list[str],
    ) -> str:
        names = {f.lower() for f in root_files}
        if "package.json" in names:
            return "node"
        if "pyproject.toml" in names or "setup.py" in names or "requirements.txt" in names:
            return "python"
        if "Cargo.toml" in names:
            return "rust"
        if "pom.xml" in names or "build.gradle" in names:
            return "java"
        if "go.mod" in names:
            return "go"
        if "ProjectType" in detected_languages or "C++" in detected_languages:
            return "cpp"
        return "unknown"

    def _detect_entry_points(self, project_type: str) -> list[str]:
        names = {f.lower() for f in self._detect_root_files()}
        entry_points: list[str] = []
        if project_type == "python":
            for candidate in ("main.py", "app.py", "cli.py", "forgex.py"):
                if candidate in names:
                    entry_points.append(candidate)
        if project_type == "node":
            for candidate in ("index.js", "main.js", "app.js", "server.js"):
                if candidate in names:
                    entry_points.append(candidate)
        return entry_points[:10]

    def _detect_dependencies(self, project_type: str) -> list[str]:
        deps: list[str] = []
        if project_type == "python":
            req = self.workspace / "requirements.txt"
            if req.exists():
                try:
                    for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            deps.append(line.split("==")[0].split(">=")[0].strip())
                except Exception:
                    pass
            py = self.workspace / "pyproject.toml"
            if py.exists():
                deps.append("pyproject.toml configured")
        return deps[:50]

    def _collect_imports(self) -> dict[str, list[str]]:
        imports: dict[str, list[str]] = {}
        try:
            for p in self.workspace.rglob("*.py"):
                rel = p.relative_to(self.workspace)
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    found: list[str] = []
                    for line in text.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("import ") or stripped.startswith("from "):
                            found.append(stripped[:120])
                    imports[str(rel)] = found[:20]
                except Exception:
                    continue
        except Exception:
            pass
        return imports

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)


__all__ = ["ContextManager", "ContextSnapshot"]
