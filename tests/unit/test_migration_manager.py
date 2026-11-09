
"""Tests for database migration management."""

import pytest

from forgex.core.exceptions import StorageError
from forgex.storage.database import Database
from forgex.storage.migrations.manager import Migration, MigrationManager


def create_users(connection):
    connection.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
        """
    )


def drop_users(connection):
    connection.execute("DROP TABLE IF EXISTS users")


def create_posts(connection):
    connection.execute(
        """
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL
        )
        """
    )


def drop_posts(connection):
    connection.execute("DROP TABLE IF EXISTS posts")


def sample_migration():
    return Migration(
        version=1,
        name="create_users",
        up=create_users,
        down=drop_users,
    )


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def manager(database):
    return MigrationManager(database)


class TestMigrationModel:

    def test_create_migration(self):
        migration = sample_migration()

        assert migration.version == 1
        assert migration.name == "create_users"
        assert callable(migration.up)
        assert callable(migration.down)

    def test_migration_requires_positive_version(self):
        with pytest.raises(ValueError):
            Migration(0, "invalid", create_users)

    def test_migration_rejects_invalid_name(self):
        with pytest.raises(ValueError):
            Migration(1, "invalid-name", create_users)

    def test_migration_checksum_is_stable(self):
        first = sample_migration()
        second = sample_migration()

        assert first.checksum == second.checksum


class TestMigrationRegistration:

    def test_register_migration(self, manager):
        migration = sample_migration()
        manager.register(migration)

        assert 1 in manager._migrations

    def test_duplicate_registration_is_rejected(self, manager):
        manager.register(sample_migration())

        with pytest.raises(StorageError):
            manager.register(sample_migration())

    def test_register_many(self, manager):
        migrations = [
            Migration(1, "create_users", create_users, drop_users),
            Migration(2, "create_posts", create_posts, drop_posts),
        ]

        manager.register_many(migrations)

        assert len(manager._migrations) == 2

    def test_register_many_rejects_duplicates(self, manager):
        migrations = [
            Migration(1, "create_users", create_users, drop_users),
            Migration(1, "create_posts", create_posts, drop_posts),
        ]

        with pytest.raises(StorageError):
            manager.register_many(migrations)

        assert len(manager._migrations) == 0


class TestMigrationApplication:

    def test_initial_version_is_zero(self, manager):
        assert manager.current_version() == 0

    def test_apply_single_migration(self, manager, database):
        manager.register(sample_migration())

        applied = manager.apply()

        assert applied == [1]
        assert manager.current_version() == 1

        cursor = database.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )

        assert cursor.fetchone() is not None

    def test_apply_multiple_migrations(self, manager):
        manager.register_many(
            [
                Migration(1, "create_users", create_users, drop_users),
                Migration(2, "create_posts", create_posts, drop_posts),
            ]
        )

        assert manager.apply() == [1, 2]
        assert manager.current_version() == 2

    def test_applied_migration_is_not_repeated(self, manager):
        manager.register(sample_migration())

        assert manager.apply() == [1]
        assert manager.apply() == []

    def test_apply_to_target_version(self, manager):
        manager.register_many(
            [
                Migration(1, "create_users", create_users, drop_users),
                Migration(2, "create_posts", create_posts, drop_posts),
            ]
        )

        assert manager.apply(target_version=1) == [1]
        assert manager.current_version() == 1

    def test_negative_target_version_is_rejected(self, manager):
        with pytest.raises(ValueError):
            manager.apply(target_version=-1)

    def test_migration_failure_rolls_back_changes(self, manager, database):

        def failing_migration(connection):
            connection.execute(
                "CREATE TABLE temporary_table (id INTEGER)"
            )
            raise RuntimeError("Migration failed")

        manager.register(
            Migration(
                1,
                "failing_migration",
                failing_migration,
            )
        )

        with pytest.raises(StorageError):
            manager.apply()

        cursor = database.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='temporary_table'
            """
        )

        assert cursor.fetchone() is None
        assert manager.current_version() == 0

    def test_migration_name_change_is_detected(self, manager):
        manager.register(sample_migration())
        manager.apply()

        manager._migrations[1] = Migration(
            version=1,
            name="renamed_users",
            up=create_users,
            down=drop_users,
        )

        with pytest.raises(StorageError):
            manager.apply()

    def test_migration_checksum_change_is_detected(self, manager):
        manager.register(sample_migration())
        manager.apply()

        def different_migration(connection):
            connection.execute(
                "CREATE TABLE different_users (id INTEGER)"
            )

        manager._migrations[1] = Migration(
            version=1,
            name="create_users",
            up=different_migration,
            down=drop_users,
        )

        with pytest.raises(StorageError):
            manager.apply()


class TestMigrationRollback:

    def test_rollback_single_migration(self, manager, database):
        manager.register(sample_migration())
        manager.apply()

        assert manager.rollback() == [1]
        assert manager.current_version() == 0

        cursor = database.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='users'
            """
        )

        assert cursor.fetchone() is None

    def test_rollback_multiple_migrations(self, manager):
        manager.register_many(
            [
                Migration(1, "create_users", create_users, drop_users),
                Migration(2, "create_posts", create_posts, drop_posts),
            ]
        )

        manager.apply()

        assert manager.rollback(steps=2) == [2, 1]
        assert manager.current_version() == 0

    def test_rollback_rejects_zero_steps(self, manager):
        with pytest.raises(ValueError):
            manager.rollback(steps=0)

    def test_rollback_rejects_excessive_steps(self, manager):
        manager.register(sample_migration())
        manager.apply()

        with pytest.raises(StorageError):
            manager.rollback(steps=2)

    def test_rollback_without_down_function_fails(self, manager):
        manager.register(
            Migration(
                version=1,
                name="create_users",
                up=create_users,
            )
        )

        manager.apply()

        with pytest.raises(StorageError):
            manager.rollback()

    def test_rollback_failure_preserves_migration_history(self, manager):

        def failing_down(connection):
            raise RuntimeError("Rollback failed")

        manager.register(
            Migration(
                version=1,
                name="create_users",
                up=create_users,
                down=failing_down,
            )
        )

        manager.apply()

        with pytest.raises(StorageError):
            manager.rollback()

        assert manager.current_version() == 1


class TestMigrationStatus:

    def test_status_before_migrations(self, manager):
        result = manager.status()

        assert result["current_version"] == 0
        assert result["registered_count"] == 0
        assert result["applied_count"] == 0
        assert result["pending_count"] == 0

    def test_status_after_registration(self, manager):
        manager.register(sample_migration())

        result = manager.status()

        assert result["registered_count"] == 1
        assert result["pending_count"] == 1

    def test_status_after_application(self, manager):
        manager.register(sample_migration())
        manager.apply()

        result = manager.status()

        assert result["current_version"] == 1
        assert result["applied_count"] == 1
        assert result["pending_count"] == 0

    def test_applied_migration_history(self, manager):
        manager.register(sample_migration())
        manager.apply()

        history = manager.applied_migrations()

        assert len(history) == 1
        assert history[0]["version"] == 1
        assert history[0]["name"] == "create_users"
        assert "checksum" in history[0]
        assert "applied_at" in history[0]
