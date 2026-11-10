
"""SQLite database infrastructure for FORGEX."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from forgex.core.exceptions import StorageError

logger = logging.getLogger(__name__)


class Database:
    """Thread-safe SQLite database manager.

    Each thread receives its own SQLite connection.
    Transactions support nested savepoints.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        timeout: float = 30.0,
        busy_timeout_ms: int = 30_000,
        enable_wal: bool = True,
        foreign_keys: bool = True,
    ) -> None:
        raw_path = str(database_path)

        self._is_memory = raw_path == ":memory:"
        self._database_target = (
            ":memory:"
            if self._is_memory
            else str(Path(database_path).expanduser().resolve())
        )

        self.database_path = Path(self._database_target)
        self.timeout = timeout
        self.busy_timeout_ms = busy_timeout_ms
        self.enable_wal = enable_wal
        self.foreign_keys = foreign_keys

        if timeout <= 0:
            raise ValueError("timeout must be positive.")

        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms cannot be negative.")

        self._local = threading.local()
        self._connections: set[sqlite3.Connection] = set()
        self._connections_lock = threading.RLock()
        self._closed = False
        self._closed_lock = threading.RLock()

        if not self._is_memory:
            Path(self._database_target).parent.mkdir(
                parents=True,
                exist_ok=True,
            )

    def _ensure_open(self) -> None:
        with self._closed_lock:
            if self._closed:
                raise StorageError("Database is closed.")

    def _create_connection(self) -> sqlite3.Connection:
        self._ensure_open()

        connection: sqlite3.Connection | None = None

        try:
            connection = sqlite3.connect(
                self._database_target,
                timeout=self.timeout,
                isolation_level=None,
                check_same_thread=False,
            )

            connection.row_factory = sqlite3.Row

            connection.execute(
                f"PRAGMA busy_timeout = {self.busy_timeout_ms}"
            )

            if self.foreign_keys:
                connection.execute("PRAGMA foreign_keys = ON")

            connection.execute("PRAGMA synchronous = NORMAL")

            if self.enable_wal and not self._is_memory:
                connection.execute("PRAGMA journal_mode = WAL")

            with self._connections_lock:
                self._ensure_open()
                self._connections.add(connection)

            logger.debug(
                "SQLite connection created for %s",
                self._database_target,
            )

            return connection

        except (sqlite3.Error, OSError, StorageError) as exc:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass

            if isinstance(exc, StorageError):
                raise

            raise StorageError(
                f"Failed to connect to database: {exc}"
            ) from exc

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the current thread's active database connection."""

        self._ensure_open()

        connection = getattr(self._local, "connection", None)

        if connection is not None:
            with self._connections_lock:
                if connection in self._connections:
                    return connection

            # The connection may have been closed by close_all().
            self._local.connection = None
            self._local.transaction_depth = 0

        connection = self._create_connection()

        self._local.connection = connection
        self._local.transaction_depth = 0

        return connection

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        """Provide a managed database cursor."""

        cursor = self.connection.cursor()

        try:
            yield cursor
        except sqlite3.Error as exc:
            raise StorageError(
                f"Database cursor operation failed: {exc}"
            ) from exc
        finally:
            cursor.close()

    def execute(
        self,
        query: str,
        parameters: tuple | dict = (),
    ) -> sqlite3.Cursor:
        """Execute a SQL statement."""

        try:
            return self.connection.execute(query, parameters)
        except sqlite3.Error as exc:
            raise StorageError(
                f"SQL execution failed: {exc}"
            ) from exc

    def executemany(
        self,
        query: str,
        parameters,
    ) -> sqlite3.Cursor:
        """Execute a SQL statement for multiple parameter sets."""

        try:
            return self.connection.executemany(query, parameters)
        except sqlite3.Error as exc:
            raise StorageError(
                f"Batch SQL execution failed: {exc}"
            ) from exc

    @contextmanager
    def transaction(
        self,
        *,
        immediate: bool = False,
    ) -> Iterator[sqlite3.Connection]:
        """Execute an atomic transaction.

        Nested transactions use SQLite savepoints.
        """

        connection = self.connection
        depth = getattr(self._local, "transaction_depth", 0)
        savepoint = f"forgex_sp_{depth}"

        try:
            if depth == 0:
                connection.execute(
                    "BEGIN IMMEDIATE" if immediate else "BEGIN"
                )
            else:
                connection.execute(f"SAVEPOINT {savepoint}")

            self._local.transaction_depth = depth + 1

            try:
                yield connection

                if depth == 0:
                    connection.commit()
                else:
                    connection.execute(
                        f"RELEASE SAVEPOINT {savepoint}"
                    )

            except Exception:
                if depth == 0:
                    connection.rollback()
                else:
                    connection.execute(
                        f"ROLLBACK TO SAVEPOINT {savepoint}"
                    )
                    connection.execute(
                        f"RELEASE SAVEPOINT {savepoint}"
                    )

                raise

        except sqlite3.Error as exc:
            raise StorageError(
                f"Database transaction failed: {exc}"
            ) from exc

        finally:
            self._local.transaction_depth = depth

    def initialize(self) -> None:
        """Initialize database-level settings."""

        try:
            connection = self.connection

            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                f"PRAGMA busy_timeout = {self.busy_timeout_ms}"
            )

            if self.enable_wal and not self._is_memory:
                connection.execute("PRAGMA journal_mode = WAL")

            logger.info(
                "Database initialized: %s",
                self._database_target,
            )

        except sqlite3.Error as exc:
            raise StorageError(
                f"Database initialization failed: {exc}"
            ) from exc

    def integrity_check(self) -> bool:
        """Run SQLite integrity_check."""

        try:
            result = self.connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()

            return result is not None and result[0] == "ok"

        except sqlite3.Error as exc:
            raise StorageError(
                f"Database integrity check failed: {exc}"
            ) from exc

    def foreign_key_check(self) -> list[sqlite3.Row]:
        """Return foreign-key constraint violations."""

        try:
            return list(
                self.connection.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            )

        except sqlite3.Error as exc:
            raise StorageError(
                f"Foreign-key check failed: {exc}"
            ) from exc

    def close_thread_connection(self) -> None:
        """Close the current thread's connection."""

        connection = getattr(self._local, "connection", None)

        if connection is None:
            return

        if getattr(self._local, "transaction_depth", 0) > 0:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass

        with self._connections_lock:
            self._connections.discard(connection)

        try:
            connection.close()
        except sqlite3.Error as exc:
            logger.warning(
                "Error closing SQLite connection: %s",
                exc,
            )

        self._local.connection = None
        self._local.transaction_depth = 0

    def close_all(self) -> None:
        """Close every registered connection without shutting down the manager.

        The manager can create fresh connections after this method returns.
        """

        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()

        for connection in connections:
            try:
                connection.close()
            except sqlite3.Error as exc:
                logger.warning(
                    "Error closing SQLite connection: %s",
                    exc,
                )

        self._local.connection = None
        self._local.transaction_depth = 0

        logger.debug(
            "All SQLite connections closed: %s",
            self._database_target,
        )

    def close(self) -> None:
        """Permanently close the database manager."""

        with self._closed_lock:
            if self._closed:
                return

            self._closed = True

        self.close_all()

        logger.info(
            "Database closed: %s",
            self._database_target,
        )

    def __enter__(self) -> Database:
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()


__all__ = ["Database"]
