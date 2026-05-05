"""Shared parallel execution helper.

Provides a thin wrapper over ``ThreadPoolExecutor`` that:
  - preserves input order in the returned results,
  - captures per-item exceptions as structured ``Result`` entries instead of
    crashing the whole batch,
  - picks a sensible default worker count when callers don't specify one.

Two variants are exposed: a sync ``run_parallel`` built on threads (correct
for I/O-bound work and GIL-releasing C extensions like BERT forward passes)
and an async ``run_parallel_async`` built on ``asyncio.gather`` (for async
native callers).
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, Iterable, Sequence, TypeVar

T = TypeVar("T")
R = TypeVar("R")


# Historical ceiling — original multi-city runs used 4 workers to avoid OOM.
# Kept here as a named constant so callers that still need it can reference it
# instead of re-hardcoding ``4``.
LEGACY_MAX_WORKERS: int = 4


@dataclass
class Result(Generic[T, R]):
    """Structured outcome for a single parallel job.

    One of ``value`` or ``error`` is always set. ``index`` matches the caller's
    input order so downstream code can reassemble position-sensitive payloads.
    """

    index: int
    item: T
    value: R | None = None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _default_max_workers(item_count: int) -> int:
    cpu = os.cpu_count() or 2
    return max(1, min(item_count, cpu * 2))


def run_parallel(
    fn: Callable[[T], R],
    items: Sequence[T] | Iterable[T],
    max_workers: int | None = None,
    timeout: float | None = None,
) -> list[Result[T, R]]:
    """Run ``fn`` over ``items`` in parallel threads.

    Args:
        fn: Callable invoked once per item.
        items: Iterable of inputs. Materialized to a list to preserve order.
        max_workers: Thread pool size. Defaults to ``min(len(items), cpu*2)``.
        timeout: Optional per-future timeout (seconds).

    Returns:
        List of ``Result`` entries in the same order as ``items``.
    """
    items_list = list(items)
    if not items_list:
        return []

    workers = max_workers if max_workers is not None else _default_max_workers(len(items_list))
    results: list[Result[T, R]] = [
        Result(index=i, item=item) for i, item in enumerate(items_list)
    ]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(fn, item): i for i, item in enumerate(items_list)
        }
        for future in as_completed(future_to_idx, timeout=timeout):
            idx = future_to_idx[future]
            try:
                results[idx].value = future.result()
            except BaseException as exc:  # noqa: BLE001 — captured per-item
                results[idx].error = exc

    return results


async def run_parallel_async(
    fn: Callable[[T], Awaitable[R]],
    items: Sequence[T] | Iterable[T],
    concurrency: int | None = None,
) -> list[Result[T, R]]:
    """Run an async ``fn`` over ``items`` concurrently.

    Uses a semaphore to cap concurrent coroutines. Per-item exceptions are
    captured into ``Result.error`` rather than raised.
    """
    items_list = list(items)
    if not items_list:
        return []

    limit = concurrency if concurrency is not None else _default_max_workers(len(items_list))
    semaphore = asyncio.Semaphore(limit)

    async def _run(i: int, item: T) -> Result[T, R]:
        async with semaphore:
            try:
                value = await fn(item)
                return Result(index=i, item=item, value=value)
            except BaseException as exc:  # noqa: BLE001
                return Result(index=i, item=item, error=exc)

    coros = [_run(i, item) for i, item in enumerate(items_list)]
    return list(await asyncio.gather(*coros))
