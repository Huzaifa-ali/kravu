"""Unit tests for run_parallel: the bounded-concurrency helper.

Offline and deterministic. Correctness is asserted order-independently (on sets),
so the same assertions hold at workers=1 (serial) and workers>1 (pooled).
"""

from __future__ import annotations

import threading
import time

import pytest

from kravu.services.parallel import run_parallel


@pytest.mark.parametrize("workers", [1, 4])
def test_run_parallel_applies_work_to_every_item(workers: int) -> None:
    seen: set[int] = set()
    lock = threading.Lock()

    def work(item: int) -> None:
        with lock:
            seen.add(item * 10)

    run_parallel([1, 2, 3, 4, 5], work, workers=workers)

    assert seen == {10, 20, 30, 40, 50}


@pytest.mark.parametrize("workers", [1, 4])
def test_run_parallel_calls_on_done_once_per_item(workers: int) -> None:
    done: list[int] = []
    lock = threading.Lock()

    def on_done(item: int) -> None:
        with lock:
            done.append(item)

    run_parallel([1, 2, 3], lambda _: None, workers=workers, on_done=on_done)

    assert sorted(done) == [1, 2, 3]


@pytest.mark.parametrize("workers", [1, 4])
def test_run_parallel_isolates_a_failing_item(workers: int) -> None:
    completed: set[int] = set()
    lock = threading.Lock()

    def work(item: int) -> None:
        if item == 3:
            raise ValueError("boom")
        with lock:
            completed.add(item)

    run_parallel([1, 2, 3, 4], work, workers=workers)

    assert completed == {1, 2, 4}


def test_run_parallel_runs_concurrently_when_workers_gt_1() -> None:
    max_in_flight = 0
    in_flight = 0
    lock = threading.Lock()

    def work(_: int) -> None:
        nonlocal max_in_flight, in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1

    run_parallel(list(range(8)), work, workers=4)

    assert max_in_flight > 1


def test_run_parallel_reraises_keyboard_interrupt() -> None:
    def work(item: int) -> None:
        if item == 1:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_parallel([1, 2, 3], work, workers=4)
