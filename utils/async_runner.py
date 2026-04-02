"""Utilities for running async code from sync pipeline nodes."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Coroutine, TypeVar

T = TypeVar("T")


def run_async(coro_factory: Callable[[], Coroutine[object, object, T]]) -> T:
    """Run an async coroutine in sync code, even if a loop is active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro_factory()))
        return future.result()
