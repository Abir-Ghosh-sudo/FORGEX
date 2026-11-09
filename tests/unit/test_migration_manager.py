
"""Database migration management for FORGEX."""

from __future__ import annotations

import hashlib
import inspect
import marshal
import re
import sqlite3

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from forgex.core.exceptions import StorageError
from forgex.storage.database import Database


MigrationOperation = Callable[[sqlite3.Connection], None]


def utc_now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Migration:
    """Represents a single database migration."""

    version: int
    name: str
    up: MigrationOperation
    down: Optional[MigrationOperation] = None

    def __post_init__(self) -> None:
        if not isinstance(self.version, int) or isinstance(self.version, bool):
            raise ValueError("Migration version must be an integer.")

        if self.version <= 0:
            raise ValueError("Migration version must be positive.")

        if not isinstance(self.name, str) or not re.fullmatch(
            r"[a-zA-Z0-9_]+", self.name
        ):
            raise ValueError(
                "Migration name must contain only letters, numbers, and underscores."
            )

        if not callable(self.up):
            raise ValueError("Migration up operation must be callable.")

        if self.down is not None and not callable(self.down):
            raise ValueError("Migration down operation must be callable.")

    @staticmethod
    def _callable_fingerprint(operation: Optional[MigrationOperation]) -> str:
        """Generate a stable representation of a migration operation."""
        if operation is None:
            return "none"

        try:
            source = inspect.getsource(operation)
            return source
        except (OSError, TypeError):
            code = getattr(operation, "__code__", None)

            if code is not None:
                return marshal.dumps(code).hex()

            return (
                f"{type(operation).__module__}."
                f"{type(operation).__qualname__}"
            )

    @property
    def checksum(self) -> str:
        """Return SHA-256 checksum of migration metadata and operations."""
        payload = "\n".join(
            (
                str(self.version),
                self.name,
                self._callable_fingerprint(self.up),
                self._callable_fingerprint(self.down),
            )
        )

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MigrationManager:
    """Register, apply, track, and rollback database migrations."""

    TABLE_NAME = "forgex_schema_migrations"

    def __init__(self, database: Database) -> None:
        self.database = database
        self._migrations: dict[int, Migration] = {}

        self._create_migration_table()

    def _create_migration_table(self) -> None:
        """Create the migration history table if it does not exist."""
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
        except Exception as exc:
            raise StorageError(
                f"Could not create migration history table: {exc}"
            ) from exc

    def register(self, migration: Migration) -> None:
        """Register one migration."""
        if not isinstance(migration, Migration):
            raise TypeError("Expected a Migration instance.")

        if migration.version in self._migrations:
            raise StorageError(
                f"Migration version {migration.version} is already registered."
            )

        self._migrations[migration.version] = migration

    def register_many(self, migrations: list[Migration]) -> None:
        """Register multiple migrations atomically."""
        versions = [migration.version for migration in migrations]

        if len(versions) != len(set(versions)):
            raise StorageError(
                "Duplicate migration versions found in registration batch."
            )

        existing = set(self._migrations)

        duplicates = existing.intersection(versions)

        if duplicates:
            version = min(duplicates)
            raise StorageError(
                f"Migration version {version} is already registered."
            )

        for migration in migrations:
            if not isinstance(migration, Migration):
                raise TypeError("Expected Migration instances.")

        for migration in migrations:
            self._migrations[migration.version] = migration

    def applied_migrations(self) -> list[dict]:
        """Return migration history ordered by version."""
        try:
            cursor = self.database.execute(
                f"""
                SELECT version, name, checksum, applied_at
                FROM {self.TABLE_NAME}
                ORDER BY version ASC
                """
            )

            return [
                {
                    "version": row["version"],
                    "name": row["name"],
                    "checksum": row["checksum"],
                    "applied_at": row["applied_at"],
                }
                for row in cursor.fetchall()
            ]
        except Exception as exc:
            raise StorageError(
                f"Could not retrieve migration history: {exc}"
            ) from exc

    def current_version(self) -> int:
        """Return the latest successfully applied migration version."""
        try:
            cursor = self.database.execute(
                f"""
                SELECT COALESCE(MAX(version), 0) AS version
                FROM {self.TABLE_NAME}
                """
            )

            row = cursor.fetchone()
            return int(row["version"]) if row else 0
        except Exception as exc:
            raise StorageError(
                f"Could not determine current migration version: {exc}"
            ) from exc

    def _validate_applied_migrations(self) -> None:
        """Detect changes to already-applied migration definitions."""
        for record in self.applied_migrations():
            version = record["version"]
            registered = self._migrations.get(version)

            if registered is None:
                raise StorageError(
                    f"Applied migration {version} is not registered."
                )

            if registered.name != record["name"]:
                raise StorageError(
                    f"Migration {version} name has changed. "
                    "Applied migration definitions must remain unchanged."
                )

            if registered.checksum != record["checksum"]:
                raise StorageError(
                    f"Migration {version} checksum mismatch. "
                    "An applied migration has been modified."
                )

    def pending_migrations(self) -> list[Migration]:
        """Return unapplied migrations after validating migration history."""
        self._validate_applied_migrations()

        applied_versions = {
            record["version"] for record in self.applied_migrations()
        }

        return [
            self._migrations[version]
            for version in sorted(self._migrations)
            if version not in applied_versions
        ]

    def apply(self, target_version: Optional[int] = None) -> list[int]:
        """Apply pending migrations up to an optional target version."""
        if target_version is not None:
            if not isinstance(target_version, int) or isinstance(
                target_version, bool
            ):
                raise ValueError("Target version must be an integer.")

            if target_version < 0:
                raise ValueError("Target version cannot be negative.")

        pending = self.pending_migrations()

        if target_version is not None:
            pending = [
                migration
                for migration in pending
                if migration.version <= target_version
            ]

        applied: list[int] = []

        for migration in pending:
            expected_version = self.current_version() + 1

            if migration.version != expected_version:
                raise StorageError(
                    f"Migration sequence gap: expected version "
                    f"{expected_version}, got {migration.version}."
                )

            try:
                with self.database.transaction() as connection:
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
                            utc_now(),
                        ),
                    )

                applied.append(migration.version)

            except Exception as exc:
                raise StorageError(
                    f"Failed to apply migration "
                    f"{migration.version} ({migration.name}): {exc}"
                ) from exc

        return applied

    def rollback(self, steps: int = 1) -> list[int]:
        """Rollback the latest applied migrations."""
        if not isinstance(steps, int) or isinstance(steps, bool):
            raise ValueError("Rollback steps must be an integer.")

        if steps <= 0:
            raise ValueError("Rollback steps must be positive.")

        self._validate_applied_migrations()

        history = self.applied_migrations()

        if steps > len(history):
            raise StorageError(
                f"Cannot rollback {steps} migrations; "
                f"only {len(history)} migrations are applied."
            )

        rolled_back: list[int] = []

        for record in reversed(history[-steps:]):
            version = record["version"]
            migration = self._migrations.get(version)

            if migration is None:
                raise StorageError(
                    f"Migration {version} is not registered."
                )

            if migration.down is None:
                raise StorageError(
                    f"Migration {version} ({migration.name}) "
                    "does not support rollback."
                )

            try:
                with self.database.transaction() as connection:
                    migration.down(connection)

                    cursor = connection.execute(
                        f"""
                        DELETE FROM {self.TABLE_NAME}
                        WHERE version = ?
                        """,
                        (version,),
                    )

                    if cursor.rowcount != 1:
                        raise StorageError(
                            f"Migration history entry {version} "
                            "could not be removed."
                        )

                rolled_back.append(version)

            except Exception as exc:
                raise StorageError(
                    f"Failed to rollback migration "
                    f"{version} ({migration.name}): {exc}"
                ) from exc

        return rolled_back

    def status(self) -> dict:
        """Return a summary of migration state."""
        history = self.applied_migrations()
        pending = self.pending_migrations()

        return {
            "current_version": self.current_version(),
            "registered_count": len(self._migrations),
            "applied_count": len(history),
            "pending_count": len(pending),
            "applied_versions": [
                record["version"] for record in history
            ],
            "pending_versions": [
                migration.version for migration in pending
            ],
        }
