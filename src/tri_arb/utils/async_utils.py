"""Async programming utilities and helpers.

Provides common utilities for async programming including
context managers, retry logic, and concurrency helpers.
"""

import asyncio
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, AsyncIterator, Callable, Optional, TypeVar

from tri_arb.config.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# Retry decorator


def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator for async functions with retry logic.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to catch and retry

    Returns:
        Decorated async function with retry logic

    Example:
        @async_retry(max_attempts=3, delay=1.0)
        async def fetch_data():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            "Retry attempts exhausted",
                            function=func.__name__,
                            attempts=max_attempts,
                            error=str(e),
                        )
                        raise

                    logger.warning(
                        "Retry attempt",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay=current_delay,
                        error=str(e),
                    )

                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            # Should never reach here, but for type checking
            raise last_exception

        return wrapper

    return decorator


# Timeout decorator


def async_timeout(seconds: float) -> Callable:
    """Decorator for async functions with timeout.

    Args:
        seconds: Timeout in seconds

    Returns:
        Decorated async function with timeout

    Example:
        @async_timeout(5.0)
        async def slow_operation():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error(
                    "Function timeout",
                    function=func.__name__,
                    timeout=seconds,
                )
                raise

        return wrapper

    return decorator


# Context managers


@asynccontextmanager
async def async_timer(name: str) -> AsyncIterator[None]:
    """Async context manager for timing code blocks.

    Args:
        name: Name of the timed block for logging

    Yields:
        None

    Example:
        async with async_timer("database_query"):
            await db.execute(query)
    """
    import time

    start = time.perf_counter()
    logger.debug("Timer started", name=name)

    try:
        yield
    finally:
        duration = time.perf_counter() - start
        logger.info("Timer finished", name=name, duration=f"{duration:.3f}s")


@asynccontextmanager
async def async_suppress(*exceptions: type[Exception]) -> AsyncIterator[None]:
    """Async context manager to suppress exceptions.

    Args:
        *exceptions: Exception types to suppress

    Yields:
        None

    Example:
        async with async_suppress(ValueError, KeyError):
            await risky_operation()
    """
    try:
        yield
    except exceptions as e:
        logger.debug("Exception suppressed", exception=type(e).__name__)


# Concurrency helpers


async def gather_with_semaphore(
    semaphore: asyncio.Semaphore,
    *tasks: Callable,
    return_exceptions: bool = False,
) -> list:
    """Execute async tasks with concurrency limit.

    Args:
        semaphore: Semaphore for concurrency control
        *tasks: Async callables to execute
        return_exceptions: Whether to return exceptions instead of raising

    Returns:
        List of results

    Example:
        semaphore = asyncio.Semaphore(5)
        results = await gather_with_semaphore(
            semaphore,
            fetch1(),
            fetch2(),
            fetch3(),
        )
    """

    async def _run_with_semaphore(task):
        async with semaphore:
            return await task

    wrapped_tasks = [_run_with_semaphore(task) for task in tasks]
    return await asyncio.gather(*wrapped_tasks, return_exceptions=return_exceptions)


async def run_with_timeout(
    coro: Callable,
    timeout: float,
    default: Optional[Any] = None,
) -> Any:
    """Run async coroutine with timeout and default value.

    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        default: Default value to return on timeout

    Returns:
        Result or default value

    Example:
        result = await run_with_timeout(
            fetch_data(),
            timeout=5.0,
            default=[],
        )
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Coroutine timeout, returning default", timeout=timeout)
        return default


# Queue utilities


class AsyncBoundedQueue:
    """Async queue with size bound and overflow handling.

    Attributes:
        maxsize: Maximum queue size
        queue: Internal asyncio.Queue
        overflow_handler: Optional callback for overflow items
    """

    def __init__(
        self,
        maxsize: int,
        overflow_handler: Optional[Callable] = None,
    ) -> None:
        """Initialize bounded queue.

        Args:
            maxsize: Maximum queue size
            overflow_handler: Optional callback for overflow items
        """
        self.maxsize = maxsize
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self.overflow_handler = overflow_handler
        logger.debug("AsyncBoundedQueue initialized", maxsize=maxsize)

    async def put(self, item: Any, block: bool = True) -> bool:
        """Put item in queue.

        Args:
            item: Item to add
            block: Whether to block when queue is full

        Returns:
            True if item was added, False if overflow occurred
        """
        if block:
            await self.queue.put(item)
            return True
        else:
            try:
                self.queue.put_nowait(item)
                return True
            except asyncio.QueueFull:
                logger.warning("Queue overflow", maxsize=self.maxsize)
                if self.overflow_handler:
                    await self.overflow_handler(item)
                return False

    async def get(self) -> Any:
        """Get item from queue.

        Returns:
            Item from queue
        """
        return await self.queue.get()

    def task_done(self) -> None:
        """Mark task as done."""
        self.queue.task_done()

    async def join(self) -> None:
        """Wait for all tasks to complete."""
        await self.queue.join()

    def qsize(self) -> int:
        """Get queue size.

        Returns:
            Current queue size
        """
        return self.queue.qsize()

    def empty(self) -> bool:
        """Check if queue is empty.

        Returns:
            True if empty, False otherwise
        """
        return self.queue.empty()

    def full(self) -> bool:
        """Check if queue is full.

        Returns:
            True if full, False otherwise
        """
        return self.queue.full()


# Rate limiting


class AsyncRateLimiter:
    """Async rate limiter using token bucket algorithm.

    Attributes:
        rate: Number of tokens per period
        period: Period in seconds
        tokens: Current token count
        updated_at: Last update timestamp
    """

    def __init__(self, rate: int, period: float = 1.0) -> None:
        """Initialize rate limiter.

        Args:
            rate: Number of tokens per period
            period: Period in seconds
        """
        self.rate = rate
        self.period = period
        self.tokens = float(rate)
        self.updated_at = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()
        logger.debug("AsyncRateLimiter initialized", rate=rate, period=period)

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire
        """
        async with self._lock:
            while tokens > self.tokens:
                await self._refill()
                if tokens > self.tokens:
                    await asyncio.sleep(0.1)

            self.tokens -= tokens

    async def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self.updated_at

        if elapsed > 0:
            new_tokens = elapsed * (self.rate / self.period)
            self.tokens = min(self.rate, self.tokens + new_tokens)
            self.updated_at = now
