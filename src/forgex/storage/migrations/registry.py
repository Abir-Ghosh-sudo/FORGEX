
"""Central registry for FORGEX database migrations."""

from __future__ import annotations

from .initial import build_initial_migration
from .manager import Migration, MigrationManager


def get_migrations() -> list[Migration]:
    """Return all built-in migrations in version order."""

    migrations = [
        build_initial_migration(),
    ]

    return sorted(migrations, key=lambda migration: migration.version)


def register_migrations(manager: MigrationManager) -> MigrationManager:
    """Register all built-in migrations with a migration manager."""

    manager.register_many(get_migrations())
    return manager


__all__ = [
    "get_migrations",
    "register_migrations",
]
