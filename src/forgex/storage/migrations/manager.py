
"""Database migration management for FORGEX."""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from forgex.core.exceptions import StorageError
from forgex.storage.database import Database

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Migration:
    """Represents a single database migration."""

    version: int
    name: str
    up: Callable[[sqlite3.Connection], None]
    down: Callable[[sqlite3.Connection], None] | None = None

    def __post_init__(self) -> None:
        if self.version <= 0:
            raise ValueError("Migration version must be positive.")

        if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.name):
            raise ValueError("Migration name contains invalid characters.")

    @property
    def checksum(self) -> str:
        """Return a stable identifier for migration metadata."""

        identity = f"{self.version}:{self.name}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class MigrationManager:
    """Register, apply, inspect, and rollback database migrations."""

    TABLE_NAME = "forgex_schema_migrations"

    def __init__(self, database: Database) -> None:
        self.database = database
        self._migrations: dict[int, Migration] = {}

        self._ensure_migration_table()

    def _ensure_migration_table(self) -> None:
        """Create the migration tracking table."""

        try:
            self.database.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
        except StorageError:
            raise
        except sqlite3.Error as exc:
            raise StorageError(
                f"Cannot initialize migration table: {exc}"
            ) from exc

    def register(self, migration: Migration) -> None:
        """Register a migration."""

        if migration.version in self._migrations:
            raise StorageError(
                f"Migration version {migration.version} is already registered."
            )

        self._migrations[migration.version] = migration

    def register_many(
        self,
        migrations: list[Migration],
    ) -> None:
        """Register multiple migrations."""

        versions = [migration.version for migration in migrations]

        if len(versions) != len(set(versions)):
            raise StorageError(
                "Duplicate migration versions detected."
            )

        for migration in sorted(
            migrations,
            key=lambda item: item.version,
        ):
            self.register(migration)

    def applied_migrations(self) -> list[dict]:
        """Return migration history."""

        try:
            rows = self.database.execute(
                f"""
                SELECT version, name, checksum, applied_at
                FROM {self.TABLE_NAME}
                ORDER BY version ASC
                """
            ).fetchall()

            return [dict(row) for row in rows]

        except sqlite3.Error as exc:
            raise StorageError(
                f"Cannot read migration history: {exc}"
            ) from exc

    def current_version(self) -> int:
        """Return the latest applied migration version."""

        row = self.database.execute(
            f"SELECT MAX(version) FROM {self.TABLE_NAME}"
        ).fetchone()

        return int(row[0] or 0)

    def pending_migrations(self) -> list[Migration]:
        """Return migrations that have not been applied."""

        applied = {
            item["version"]: item
            for item in self.applied_migrations()
        }

        pending = []

        for version, migration in sorted(self._migrations.items()):
            existing = applied.get(version)

            if existing is None:
                pending.append(migration)
                continue

            if existing["name"] != migration.name:
                raise StorageError(
                    f"Migration {version} name has changed."
                )

            if existing["checksum"] != migration.checksum:
                raise StorageError(
                    f"Migration {version} checksum mismatch."
                )

        return pending

    def apply(
        self,
        target_version: int | None = None,
    ) -> list[int]:
        """Apply pending migrations sequentially.

        Returns the versions successfully applied.
        """

        pending = self.pending_migrations()

        if target_version is not None and target_version < 0:
            raise ValueError("target_version cannot be negative.")

        if target_version is not None:
            pending = [
                migration
                for migration in pending
                if migration.version <= target_version
            ]

        applied_versions = []

        for migration in pending:
            with self.database.transaction(immediate=True) as connection:
                try:
                    migration.up(connection)

                    connection.execute(
                        f"""
                        INSERT INTO {self.TABLE_NAME}
                        (version, name, checksum, applied_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            migration.version,
                            migration.name,
                            migration.checksum,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )

                except Exception as exc:
                    logger.exception(
                        "Migration %s failed.",
                        migration.version,
                    )

                    raise StorageError(
                        f"Migration {migration.version} "
                        f"({migration.name}) failed: {exc}"
                    ) from exc

            applied_versions.append(migration.version)

            logger.info(
                "Applied migration %s: %s",
                migration.version,
                migration.name,
            )

        return applied_versions

    def rollback(
        self,
        steps: int = 1,
    ) -> list[int]:
        """Rollback the latest applied migrations.

        A migration without a down function cannot be rolled back.
        """

        if steps <= 0:
            raise ValueError("steps must be positive.")

        history = self.applied_migrations()

        if steps > len(history):
            raise StorageError(
                "Cannot rollback more migrations than have been applied."
            )

        rolled_back = []

        for item in reversed(history[-steps:]):
            migration = self._migrations.get(item["version"])

            if migration is None:
                raise StorageError(
                    f"Migration {item['version']} is not registered."
                )

            if migration.down is None:
                raise StorageError(
                    f"Migration {item['version']} does not support rollback."
                )

            if migration.checksum != item["checksum"]:
                raise StorageError(
                    f"Migration {item['version']} checksum mismatch."
                )

            with self.database.transaction(immediate=True) as connection:
                try:
                    migration.down(connection)

                    connection.execute(
                        f"""
                        DELETE FROM {self.TABLE_NAME}
                        WHERE version = ?
                        """,
                        (migration.version,),
                    )

                except Exception as exc:
                    logger.exception(
                        "Rollback of migration %s failed.",
                        migration.version,
                    )

                    raise StorageError(
                        f"Rollback of migration {migration.version} failed: {exc}"
                    ) from exc

            rolled_back.append(migration.version)

            logger.info(
                "Rolled back migration %s: %s",
                migration.version,
                migration.name,
            )

        return rolled_back

    def status(self) -> dict:
        """Return a complete migration status report."""

        history = self.applied_migrations()
        pending = self.pending_migrations()

        return {
            "current_version": self.current_version(),
            "registered_count": len(self._migrations),
            "applied_count": len(history),
            "pending_count": len(pending),
            "applied": history,
            "pending": [
                {
                    "version": migration.version,
                    "name": migration.name,
                }
                for migration in pending
            ],
        }
