"""Database migration management for FORGEX."""

from __future__ import annotations

import hashlib
import logging
import marshal
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from forgex.core.exceptions import StorageError
from forgex.storage.database import Database

logger = logging.getLogger(__name__)

MigrationOperation = Callable[[sqlite3.Connection], None]


def utc_now() -> str:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Migration:
    """Represents a single database migration."""

    version: int
    name: str
    up: MigrationOperation
    down: MigrationOperation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version <= 0:
            raise ValueError("Migration version must be a positive integer.")

        if not isinstance(self.name, str):
            raise ValueError("Migration name must be a string.")

        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError(
                "Migration name must start with a lowercase letter "
                "and contain only lowercase letters, numbers, "
                "and underscores."
            )

        if not callable(self.up):
            raise ValueError("Migration up operation must be callable.")

        if self.down is not None and not callable(self.down):
            raise ValueError("Migration down operation must be callable.")

    @staticmethod
    def _operation_fingerprint(
        operation: MigrationOperation | None,
    ) -> str:
        """Generate a deterministic fingerprint for an operation."""

        if operation is None:
            return "none"

        digest = hashlib.sha256()

        code = getattr(operation, "__code__", None)

        if code is not None:
            digest.update(marshal.dumps(code))

            defaults = repr(getattr(operation, "__defaults__", None))
            keyword_defaults = repr(getattr(operation, "__kwdefaults__", None))

            digest.update(defaults.encode("utf-8"))
            digest.update(keyword_defaults.encode("utf-8"))

            closure = getattr(operation, "__closure__", None)

            if closure:
                for cell in closure:
                    try:
                        value = repr(cell.cell_contents)
                    except ValueError:
                        value = "<empty-cell>"

                    digest.update(value.encode("utf-8"))

        else:
            identity = f"{type(operation).__module__}.{type(operation).__qualname__}"
            digest.update(identity.encode("utf-8"))

        return digest.hexdigest()

    @property
    def checksum(self) -> str:
        """Return a stable checksum of the complete migration."""

        payload = "|".join(
            (
                str(self.version),
                self.name,
                self._operation_fingerprint(self.up),
                self._operation_fingerprint(self.down),
            )
        )

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
            raise StorageError(f"Cannot initialize migration table: {exc}") from exc

    def register(self, migration: Migration) -> None:
        """Register one migration."""

        if not isinstance(migration, Migration):
            raise TypeError("Expected a Migration instance.")

        if migration.version in self._migrations:
            raise StorageError(f"Migration version {migration.version} is already registered.")

        self._migrations[migration.version] = migration

    def register_many(
        self,
        migrations: list[Migration],
    ) -> None:
        """Register multiple migrations atomically."""

        for migration in migrations:
            if not isinstance(migration, Migration):
                raise TypeError("All entries must be Migration instances.")

        versions = [migration.version for migration in migrations]

        if len(versions) != len(set(versions)):
            raise StorageError("Duplicate migration versions detected.")

        duplicates = set(versions).intersection(self._migrations)

        if duplicates:
            version = min(duplicates)
            raise StorageError(f"Migration version {version} is already registered.")

        for migration in migrations:
            self._migrations[migration.version] = migration

    def applied_migrations(self) -> list[dict]:
        """Return migration history ordered by version."""

        try:
            rows = self.database.execute(
                f"""
                SELECT version, name, checksum, applied_at
                FROM {self.TABLE_NAME}
                ORDER BY version ASC
                """
            ).fetchall()

            return [dict(row) for row in rows]

        except (sqlite3.Error, StorageError) as exc:
            raise StorageError(f"Cannot read migration history: {exc}") from exc

    def current_version(self) -> int:
        """Return the latest successfully applied migration version."""

        try:
            row = self.database.execute(
                f"""
                SELECT COALESCE(MAX(version), 0)
                FROM {self.TABLE_NAME}
                """
            ).fetchone()

            return int(row[0]) if row else 0

        except (sqlite3.Error, StorageError) as exc:
            raise StorageError(f"Cannot determine current migration version: {exc}") from exc

    def _validate_applied_migrations(self) -> None:
        """Ensure applied migration definitions have not changed."""

        history = self.applied_migrations()

        for item in history:
            version = item["version"]
            migration = self._migrations.get(version)

            if migration is None:
                raise StorageError(f"Applied migration {version} is not registered.")

            if migration.name != item["name"]:
                raise StorageError(f"Migration {version} name has changed.")

            if migration.checksum != item["checksum"]:
                raise StorageError(
                    f"Migration {version} checksum mismatch. "
                    "An applied migration has been modified."
                )

    def pending_migrations(self) -> list[Migration]:
        """Return migrations that have not been applied."""

        self._validate_applied_migrations()

        applied_versions = {item["version"] for item in self.applied_migrations()}

        return [
            migration
            for version, migration in sorted(self._migrations.items())
            if version not in applied_versions
        ]

    def apply(
        self,
        target_version: int | None = None,
    ) -> list[int]:
        """Apply pending migrations sequentially."""

        if target_version is not None:
            if not isinstance(target_version, int) or isinstance(target_version, bool):
                raise ValueError("target_version must be an integer.")

            if target_version < 0:
                raise ValueError("target_version cannot be negative.")

        pending = self.pending_migrations()

        if target_version is not None:
            pending = [migration for migration in pending if migration.version <= target_version]

        applied_versions: list[int] = []

        for migration in pending:
            expected_version = self.current_version() + 1

            if migration.version != expected_version:
                raise StorageError(
                    f"Migration sequence gap: expected version "
                    f"{expected_version}, got {migration.version}."
                )

            try:
                with self.database.transaction(immediate=True) as connection:
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

            except Exception as exc:
                logger.exception(
                    "Migration %s failed.",
                    migration.version,
                )

                raise StorageError(
                    f"Migration {migration.version} ({migration.name}) failed: {exc}"
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
        """Rollback the latest applied migrations."""

        if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
            raise ValueError("steps must be a positive integer.")

        self._validate_applied_migrations()

        history = self.applied_migrations()

        if steps > len(history):
            raise StorageError("Cannot rollback more migrations than have been applied.")

        rolled_back: list[int] = []

        for item in reversed(history[-steps:]):
            version = item["version"]
            migration = self._migrations.get(version)

            if migration is None:
                raise StorageError(f"Migration {version} is not registered.")

            if migration.down is None:
                raise StorageError(f"Migration {version} does not support rollback.")

            if migration.checksum != item["checksum"]:
                raise StorageError(f"Migration {version} checksum mismatch.")

            try:
                with self.database.transaction(immediate=True) as connection:
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
                            f"Migration history entry {version} could not be removed."
                        )

            except Exception as exc:
                logger.exception(
                    "Rollback of migration %s failed.",
                    version,
                )

                raise StorageError(
                    f"Rollback of migration {version} ({migration.name}) failed: {exc}"
                ) from exc

            rolled_back.append(version)

            logger.info(
                "Rolled back migration %s: %s",
                version,
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
