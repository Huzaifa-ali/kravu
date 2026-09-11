"""Bounded-concurrency helper for running per-item work across a pipeline step.

Single responsibility: apply a ``work`` callable to every item in a batch, with
an optional ``on_done`` callback per item, either serially (``workers <= 1``) or
across a bounded thread pool (``workers > 1``). This module holds no business
logic — it is the sequencing primitive the per-job use cases will build on.

Contract:
    * A per-item failure raised by ``work`` is CONTAINED: it is logged and that
      item is skipped so one bad item never aborts the whole batch.
    * ``KeyboardInterrupt`` is the sole exception to containment — it always
      propagates. In the pooled path, not-yet-started items are cancelled,
      in-flight items are allowed to finish, and the interrupt is re-raised.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TypeVar

_LOGGER = logging.getLogger("kravu")

T = TypeVar("T")

StoreFactory = Callable[[], object]
"""Factory that produces a fresh per-thread resource (e.g. a store connection).

Defined here so callers that fan work out across threads have a single named
type for "make me a new isolated resource" without threading it through this
helper's signature.
"""


def run_parallel(
    items: list[T],
    work: Callable[[T], None],
    *,
    workers: int,
    on_done: Callable[[T], None] | None = None,
) -> None:
    """Apply ``work`` to every item, optionally across a bounded thread pool.

    Args:
        items: The batch to process.
        work: Side-effecting callable invoked once per item. A raised
            ``Exception`` is contained (logged, item skipped); a
            ``KeyboardInterrupt`` propagates.
        workers: Degree of concurrency. ``<= 1`` runs a plain serial loop;
            ``> 1`` uses a thread pool of that size.
        on_done: Optional callback invoked once per item after its ``work``
            returns (serial path) or completes (pooled path). It always runs on
            the calling thread (never a pool worker), so it needs no locking of
            its own — the thread-safe progress reporter aside.

    Raises:
        KeyboardInterrupt: If ``work`` raises it, or the run is interrupted.
    """
    if workers <= 1:
        _run_serial(items, work, on_done)
        return
    _run_pooled(items, work, workers, on_done)


def _run_serial(
    items: list[T],
    work: Callable[[T], None],
    on_done: Callable[[T], None] | None,
) -> None:
    """Process items one at a time, containing per-item failures."""
    for item in items:
        _do_one(item, work)
        if on_done is not None:
            on_done(item)


def _run_pooled(
    items: list[T],
    work: Callable[[T], None],
    workers: int,
    on_done: Callable[[T], None] | None,
) -> None:
    """Process items across a bounded thread pool, containing per-item failures.

    On ``KeyboardInterrupt``, not-yet-started futures are cancelled, in-flight
    ones are allowed to finish, and the interrupt is re-raised.
    """
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[Future[None], T] = {
            executor.submit(_do_one, item, work): item for item in items
        }
        try:
            for future in as_completed(futures):
                future.result()
                if on_done is not None:
                    on_done(futures[future])
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()
            raise


def _do_one(item: T, work: Callable[[T], None]) -> None:
    """Run ``work`` for one item, containing any non-interrupt exception.

    A ``KeyboardInterrupt`` propagates; every other ``Exception`` is logged and
    swallowed so the surrounding batch continues.
    """
    try:
        work(item)
    except KeyboardInterrupt:
        raise
    except Exception:
        _LOGGER.exception("parallel: item failed and was skipped: %r", item)
