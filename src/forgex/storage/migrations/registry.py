"""Central registry for FORGEX database migrations."""

from collections.abc import Iterable

from .initial import build_initial_migration
from .manager import Migration
from .memory import build_memory_migration


def get_migrations() -> list[Migration]:
    """Return all built-in migrations in version order."""
    migrations = [
        build_initial_migration(),
        build_memory_migration(),
    ]

    return sorted(migrations, key=lambda migration: migration.version)


def register_migrations(
    migrations: Iterable[Migration],
) -> list[Migration]:
    """Merge custom migrations with built-in migrations.

    Raises:
        ValueError: If two migrations use the same version.
    """
    combined = [*get_migrations(), *migrations]
    combined.sort(key=lambda migration: migration.version)

    versions: set[int] = set()

    for migration in combined:
        if migration.version in versions:
            raise ValueError(f"Duplicate migration version: {migration.version}")
        versions.add(migration.version)

    return combined


__all__ = [
    "get_migrations",
    "register_migrations",
]
