"""Git repository management commands for FORGEX."""

from __future__ import annotations

from pathlib import Path

import typer
from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="git",
    help="Inspect and manage Git repositories.",
    no_args_is_help=True,
)

console = Console()


def _get_repo(path: Path) -> Repo:
    """Find the Git repository containing the selected workspace."""
    try:
        return Repo(path.expanduser().resolve(strict=True), search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError, OSError) as exc:
        raise typer.BadParameter(f"No Git repository found for: {path}") from exc


def _relative_path(repo: Repo) -> str:
    """Return the repository root path."""
    return str(Path(repo.working_tree_dir or repo.git_dir).resolve())


@app.command("status")
def git_status(
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Repository workspace.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
) -> None:
    """Display the current Git repository status."""
    repo = _get_repo(workspace)

    console.print(f"\n[bold cyan]Repository:[/bold cyan] {_relative_path(repo)}")

    if repo.bare:
        console.print("[yellow]This is a bare Git repository.[/yellow]")
        return

    console.print(
        f"[bold]Branch:[/bold] "
        f"{repo.active_branch.name if not repo.head.is_detached else 'Detached HEAD'}"
    )

    if repo.head.is_valid():
        console.print(f"[bold]HEAD:[/bold] {repo.head.commit.hexsha[:12]}")
    else:
        console.print("[yellow]Repository has no commits yet.[/yellow]")

    changed = repo.index.diff(None)
    staged = repo.index.diff("HEAD") if repo.head.is_valid() else []

    untracked = repo.untracked_files

    table = Table(title="Working Tree Changes")
    table.add_column("Status", style="cyan")
    table.add_column("File")

    for item in staged:
        table.add_row("[green]STAGED[/green]", item.a_path or item.b_path or "")

    for item in changed:
        table.add_row("[yellow]MODIFIED[/yellow]", item.a_path or item.b_path or "")

    for filename in untracked:
        table.add_row("[dim]UNTRACKED[/dim]", filename)

    if table.row_count == 0:
        console.print("[green]Working tree is clean.[/green]")
    else:
        console.print(table)


@app.command("branches")
def git_branches(
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Repository workspace.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
) -> None:
    """List local Git branches."""
    repo = _get_repo(workspace)

    table = Table(title="Git Branches")
    table.add_column("Current", justify="center")
    table.add_column("Branch", style="cyan")

    current = repo.active_branch.name if not repo.head.is_detached else None

    for branch in repo.branches:
        table.add_row(
            "[green]*[/green]" if branch.name == current else "",
            branch.name,
        )

    console.print(table)


@app.command("log")
def git_log(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
        max=100,
        help="Maximum number of commits to display.",
    ),
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Repository workspace.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
) -> None:
    """Display recent Git commits."""
    repo = _get_repo(workspace)

    if not repo.head.is_valid():
        console.print("[yellow]No commits found.[/yellow]")
        return

    table = Table(title="Recent Commits")
    table.add_column("Commit", style="cyan")
    table.add_column("Author")
    table.add_column("Date")
    table.add_column("Message", overflow="fold")

    for commit in repo.iter_commits(max_count=limit):
        table.add_row(
            commit.hexsha[:10],
            commit.author.name or "Unknown",
            commit.committed_datetime.strftime("%Y-%m-%d %H:%M"),
            commit.message.strip().splitlines()[0],
        )

    console.print(table)


@app.command("diff")
def git_diff(
    staged: bool = typer.Option(
        False,
        "--staged",
        help="Show staged changes instead of unstaged changes.",
    ),
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Repository workspace.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
) -> None:
    """Display Git differences."""
    repo = _get_repo(workspace)

    try:
        if staged:
            if not repo.head.is_valid():
                console.print(
                    "[yellow]No HEAD commit exists; staged diff cannot be calculated.[/yellow]"
                )
                return

            diff = repo.git.diff("--cached", "--no-ext-diff", "--")
        else:
            diff = repo.git.diff("--no-ext-diff", "--")

        if not diff.strip():
            console.print("[dim]No differences found.[/dim]")
            return

        console.print(diff)

    except GitCommandError as exc:
        console.print(f"[red]Git diff failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("create-branch")
def create_branch(
    name: str = typer.Argument(
        ...,
        help="Name of the new branch.",
    ),
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Repository workspace.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
) -> None:
    """Create and switch to a new Git branch."""
    name = name.strip()

    if not name:
        raise typer.BadParameter("Branch name cannot be empty.")

    repo = _get_repo(workspace)

    try:
        if not repo.head.is_valid():
            raise typer.BadParameter("Cannot create a branch before the first commit.")

        if not repo.git.check_ref_format(f"refs/heads/{name}"):
            raise typer.BadParameter("Invalid Git branch name.")

        if name in [branch.name for branch in repo.branches]:
            raise typer.BadParameter(f"Branch already exists: {name}")

        branch = repo.create_head(name)
        branch.checkout()

        console.print(f"[green]Created and switched to branch:[/green] {name}")

    except GitCommandError as exc:
        console.print(f"[red]Branch creation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("checkout")
def checkout_branch(
    name: str = typer.Argument(
        ...,
        help="Existing local branch name.",
    ),
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Repository workspace.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
) -> None:
    """Switch to an existing local branch."""
    repo = _get_repo(workspace)

    if name not in [branch.name for branch in repo.branches]:
        raise typer.BadParameter(f"Local branch not found: {name}")

    if repo.is_dirty(untracked_files=True):
        raise typer.BadParameter(
            "Working tree has uncommitted changes. "
            "Commit or safely preserve them before switching branches."
        )

    try:
        repo.git.checkout(name)
        console.print(f"[green]Switched to branch:[/green] {name}")

    except GitCommandError as exc:
        console.print(f"[red]Checkout failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
