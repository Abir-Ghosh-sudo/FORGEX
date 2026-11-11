"""Retry, backoff, and timeout utilities for FORGEX."""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class RetryExhaustedError(RuntimeError):
    """Raised when all retry attempts have failed."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_exception: Exception,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception


def calculate_backoff(
    attempt: int,
    *,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
) -> float:
    """Calculate exponential backoff with optional jitter."""

    if attempt < 1:
        raise ValueError("attempt must be at least 1.")

    if base_delay < 0:
        raise ValueError("base_delay cannot be negative.")

    if max_delay < 0:
        raise ValueError("max_delay cannot be negative.")

    if exponential_base < 1:
        raise ValueError("exponential_base must be at least 1.")

    delay = min(
        base_delay * exponential_base ** (attempt - 1),
        max_delay,
    )

    if jitter:
        delay = random.uniform(0.5 * delay, delay)

    return delay


def retry(
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int, float], None] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry a synchronous function after selected exceptions."""

    if attempts < 1:
        raise ValueError("attempts must be at least 1.")

    if not exceptions:
        raise ValueError("At least one retryable exception is required.")

    def decorator(
        function: Callable[P, R],
    ) -> Callable[P, R]:
        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Exception | None = None

            for attempt in range(1, attempts + 1):
                try:
                    return function(*args, **kwargs)

                except exceptions as exc:
                    last_exception = exc

                    if attempt == attempts:
                        break

                    delay = calculate_backoff(
                        attempt,
                        base_delay=base_delay,
                        max_delay=max_delay,
                        exponential_base=exponential_base,
                        jitter=jitter,
                    )

                    logger.warning(
                        "%s failed (attempt %d/%d). Retrying in %.2fs: %s",
                        function.__qualname__,
                        attempt,
                        attempts,
                        delay,
                        exc,
                    )

                    if on_retry is not None:
                        on_retry(exc, attempt, delay)

                    time.sleep(delay)

            assert last_exception is not None

            raise RetryExhaustedError(
                f"{function.__qualname__} failed after {attempts} attempts.",
                attempts=attempts,
                last_exception=last_exception,
            ) from last_exception

        return wrapper

    return decorator


def async_retry(
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: (Callable[[Exception, int, float], Any] | None) = None,
) -> Callable[
    [Callable[P, Awaitable[R]]],
    Callable[P, Awaitable[R]],
]:
    """Retry an asynchronous function without blocking the event loop."""

    if attempts < 1:
        raise ValueError("attempts must be at least 1.")

    if not exceptions:
        raise ValueError("At least one retryable exception is required.")

    def decorator(
        function: Callable[P, Awaitable[R]],
    ) -> Callable[P, Awaitable[R]]:
        @functools.wraps(function)
        async def wrapper(
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> R:
            last_exception: Exception | None = None

            for attempt in range(1, attempts + 1):
                try:
                    return await function(*args, **kwargs)

                except exceptions as exc:
                    last_exception = exc

                    if attempt == attempts:
                        break

                    delay = calculate_backoff(
                        attempt,
                        base_delay=base_delay,
                        max_delay=max_delay,
                        exponential_base=exponential_base,
                        jitter=jitter,
                    )

                    logger.warning(
                        "%s failed (attempt %d/%d). Retrying in %.2fs: %s",
                        function.__qualname__,
                        attempt,
                        attempts,
                        delay,
                        exc,
                    )

                    if on_retry is not None:
                        callback_result = on_retry(
                            exc,
                            attempt,
                            delay,
                        )

                        if asyncio.iscoroutine(callback_result):
                            await callback_result

                    await asyncio.sleep(delay)

            assert last_exception is not None

            raise RetryExhaustedError(
                f"{function.__qualname__} failed after {attempts} attempts.",
                attempts=attempts,
                last_exception=last_exception,
            ) from last_exception

        return wrapper

    return decorator


async def run_with_timeout(
    awaitable: Awaitable[R],
    timeout: float,
) -> R:
    """Execute an awaitable with a maximum time limit."""

    if timeout <= 0:
        raise ValueError("timeout must be greater than zero.")

    try:
        async with asyncio.timeout(timeout):
            return await awaitable
    except TimeoutError:
        logger.warning(
            "Operation exceeded timeout of %.2f seconds.",
            timeout,
        )
        raise


__all__ = [
    "RetryExhaustedError",
    "calculate_backoff",
    "retry",
    "async_retry",
    "run_with_timeout",
]
