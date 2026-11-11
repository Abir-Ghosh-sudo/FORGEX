"""Workspace analysis command for FORGEX."""

from __future__ import annotations

import contextlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forgex.utils.paths import get_platform_name, normalize_path

app = typer.Typer(
    name="analyze",
    help="Inspect and analyze a software project.",
)

console = Console()

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".next",
    ".nuxt",
    "dist",
    "build",
    "target",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "coverage",
}

IMPORTANT_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "CMakeLists.txt",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "README.md",
    "LICENSE",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
}

LANGUAGE_MAP = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".h": "C/C++ Header",
    ".c": "C",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".dart": "Dart",
    ".r": "R",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Batch",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".ipynb": "Jupyter Notebook",
}


@dataclass(slots=True)
class AnalysisResult:
    """Aggregated workspace analysis information."""

    root: Path
    total_files: int
    total_directories: int
    total_size: int
    languages: Counter[str]
    important_files: list[str]
    top_level_entries: list[str]
    truncated: bool


def _human_size(size: int) -> str:
    """Convert bytes to a readable size."""
    value = float(size)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024

    return f"{value:.2f} TB"


def analyze_workspace(
    workspace: Path,
    max_files: int = 100_000,
) -> AnalysisResult:
    """Analyze a workspace without reading file contents."""
    root = normalize_path(workspace)

    if not root.exists() or not root.is_dir():
        raise ValueError(f"Workspace directory does not exist: {root}")

    if max_files < 1:
        raise ValueError("max_files must be greater than zero.")

    languages: Counter[str] = Counter()
    important_files: list[str] = []
    top_level_entries: list[str] = []

    total_files = 0
    total_directories = 0
    total_size = 0
    truncated = False

    with contextlib.suppress(OSError):
        top_level_entries = sorted(
            entry.name + ("/" if entry.is_dir() else "") for entry in root.iterdir()
        )

    def walk_error(_: OSError) -> None:
        # Unreadable directories are skipped rather than aborting analysis.
        return

    for current_root, directories, filenames in __import__("os").walk(
        root,
        topdown=True,
        onerror=walk_error,
        followlinks=False,
    ):
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES
            and not (Path(current_root) / directory).is_symlink()
        )

        total_directories += len(directories)

        current_path = Path(current_root)

        for filename in sorted(filenames):
            file_path = current_path / filename

            if file_path.is_symlink():
                continue

            if total_files >= max_files:
                truncated = True
                break

            try:
                stat = file_path.stat()
            except OSError:
                continue

            if not file_path.is_file():
                continue

            total_files += 1
            total_size += stat.st_size

            language = LANGUAGE_MAP.get(file_path.suffix.lower())

            if language:
                languages[language] += 1

            if filename in IMPORTANT_FILES:
                try:
                    relative = file_path.relative_to(root)
                    important_files.append(relative.as_posix())
                except ValueError:
                    continue

        if truncated:
            break

    return AnalysisResult(
        root=root,
        total_files=total_files,
        total_directories=total_directories,
        total_size=total_size,
        languages=languages,
        important_files=sorted(important_files),
        top_level_entries=top_level_entries,
        truncated=truncated,
    )


def _render_analysis(result: AnalysisResult) -> None:
    """Render analysis results in the terminal."""
    console.print()
    console.print(
        Panel(
            f"[bold cyan]{result.root}[/bold cyan]\n[dim]Platform: {get_platform_name()}[/dim]",
            title="FORGEX Project Analysis",
            border_style="cyan",
        )
    )

    summary = Table(title="Project Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right")

    summary.add_row("Files", f"{result.total_files:,}")
    summary.add_row("Directories", f"{result.total_directories:,}")
    summary.add_row("Total Size", _human_size(result.total_size))

    console.print(summary)

    if result.languages:
        language_table = Table(title="Language Distribution")
        language_table.add_column("Language", style="cyan")
        language_table.add_column("Files", justify="right")
        language_table.add_column("Share", justify="right")

        for language, count in result.languages.most_common():
            percentage = count / result.total_files * 100
            language_table.add_row(
                language,
                f"{count:,}",
                f"{percentage:.1f}%",
            )

        console.print(language_table)
    else:
        console.print("[dim]No recognized source file extensions found.[/dim]")

    if result.important_files:
        important_table = Table(title="Important Project Files")
        important_table.add_column("File", style="green")

        for filename in result.important_files:
            important_table.add_row(filename)

        console.print(important_table)

    if result.top_level_entries:
        console.print()
        console.print("[bold]Top-level entries[/bold]")

        for entry in result.top_level_entries[:30]:
            console.print(f"  {entry}")

        if len(result.top_level_entries) > 30:
            console.print(f"  [dim]... and {len(result.top_level_entries) - 30} more[/dim]")

    if result.truncated:
        console.print(
            "\n[yellow]Analysis reached its file limit. Some files may not be included.[/yellow]"
        )


@app.command("workspace")
def analyze_command(
    path: Path | None = typer.Argument(
        None,
        help="Project directory to analyze (defaults to current directory).",
    ),
    max_files: int = typer.Option(
        100_000,
        "--max-files",
        min=1,
        help="Maximum number of files to inspect.",
    ),
) -> None:
    """Analyze the structure and languages of a workspace."""
    target_path = Path.cwd() if path is None else Path(path).resolve()
    try:
        result = analyze_workspace(target_path, max_files=max_files)
        _render_analysis(result)
    except (ValueError, OSError) as exc:
        console.print(f"[red]Project analysis failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
