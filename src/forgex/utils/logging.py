"""Centralized logging configuration for FORGEX."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from threading import RLock

from forgex.config.settings import LoggingSettings


class ForgexLogger:
    """Centralized logger factory and configuration manager."""

    _lock = RLock()
    _configured = False
    _loggers: dict[str, logging.Logger] = []

    @classmethod
    def configure(
        cls,
        settings: LoggingSettings,
        *,
        force: bool = False,
    ) -> None:
        """Configure application-wide logging handlers."""

        with cls._lock:
            root_logger = logging.getLogger("forgex")

            if cls._configured and not force:
                return

            cls._close_handlers(root_logger)
            root_logger.setLevel(settings.level)
            root_logger.propagate = False

            formatter = logging.Formatter(
                fmt=(
                    "%(asctime)s | %(levelname)-8s | "
                    "%(name)s | %(message)s"
                ),
                datefmt="%Y-%m-%d %H:%M:%S",
            )

            if settings.console_enabled:
                console_handler = logging.StreamHandler(sys.stderr)
                console_handler.setFormatter(formatter)
                root_logger.addHandler(console_handler)

            if settings.file_enabled:
                settings.log_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                file_handler = (
                    logging.handlers.RotatingFileHandler(
                        filename=settings.log_dir / "forgex.log",
                        maxBytes=settings.max_file_size_mb * 1024 * 1024,
                        backupCount=settings.backup_count,
                        encoding="utf-8",
                        delay=True,
                    )
                )

                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)

            cls._configured = True

    @classmethod
    def get_logger(
        cls,
        name: str,
    ) -> logging.Logger:
        """Get a named logger within the FORGEX namespace."""

        if not name or not name.strip():
            raise ValueError("Logger name cannot be empty.")

        normalized_name = name.strip()

        if normalized_name == "forgex":
            logger_name = "forgex"
        elif normalized_name.startswith("forgex."):
            logger_name = normalized_name
        else:
            logger_name = f"forgex.{normalized_name}"

        logger = logging.getLogger(logger_name)

        with cls._lock:
            cls._loggers[logger_name] = logger

        return logger

    @classmethod
    def shutdown(cls) -> None:
        """Flush and close FORGEX logging handlers."""

        with cls._lock:
            root_logger = logging.getLogger("forgex")
            cls._close_handlers(root_logger)
            cls._configured = False

    @staticmethod
    def _close_handlers(logger: logging.Logger) -> None:
        """Safely flush and close all handlers."""

        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

            try:
                handler.flush()
            finally:
                handler.close()


def configure_logging(
    settings: LoggingSettings,
    *,
    force: bool = False,
) -> None:
    """Convenience function for configuring FORGEX logging."""

    ForgexLogger.configure(settings, force=force)


def get_logger(name: str) -> logging.Logger:
    """Convenience function for retrieving a FORGEX logger."""

    return ForgexLogger.get_logger(name)


def shutdown_logging() -> None:
    """Convenience function for shutting down FORGEX logging."""

    ForgexLogger.shutdown()


__all__ = [
    "ForgexLogger",
    "configure_logging",
    "get_logger",
    "shutdown_logging",
]