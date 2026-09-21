"""Deterministic lifecycle checks; real fork isolated by a subprocess timeout."""

import gc
import os
import subprocess
import sys
import textwrap
import threading
import weakref
from pathlib import Path

import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_context_lifecycle import ForkSafeSharedContextPool
from benchmarks.compressed_shared_context import independent_compress


def test_weak_registry_does_not_retain_pools():
    pool = ForkSafeSharedContextPool()
    reference = weakref.ref(pool)
    del pool
    gc.collect()
    assert reference() is None


@pytest.mark.parametrize("codec", ["lz4", "zstd"])
def test_length_keys_bounds_and_failure_drop(codec):
    pool = ForkSafeSharedContextPool(max_contexts=2, max_payload=512)
    for raw in (bytes(range(64)), bytes(range(65)), bytes(range(66)), bytes(513)):
        assert pool.compress(codec, raw, False) == independent_compress(
            codec, raw, False
        )
    assert set(pool._entries) == {(codec, False, 64), (codec, False, 65)}
    assert pool.info()["contexts"] == 2
    entry = pool._entries[(codec, False, 64)]

    class Failing:
        def update_data(self, *args, **kwargs):
            raise RuntimeError("injected")

    entry.context = Failing()
    with pytest.raises(RuntimeError, match="injected"):
        pool.compress(codec, bytes(range(64)), False)
    assert (codec, False, 64) not in pool._entries
    assert pool._active == 0
    assert pool.info()["counters"]["dropped_failure"] == 1
    pool.clear()
    assert pool.info()["contexts"] == 0


def _quiescence_scenario():
    pool = ForkSafeSharedContextPool()
    entered = threading.Event()
    release = threading.Event()
    original = pool._new_context

    def paused(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    pool._new_context = paused
    worker = threading.Thread(
        target=pool.compress, args=("lz4", bytes(range(64)), False)
    )
    worker.start()
    assert entered.wait(3)
    prepared = threading.Event()
    finish = threading.Event()

    def quiesce():
        pool._prepare_fork()
        prepared.set()
        assert finish.wait(3)
        pool._finish_parent()

    waiter = threading.Thread(target=quiesce)
    waiter.start()
    # Synchronize on the condition, not sleep or a scheduling assumption.
    with pool._condition:
        while not pool._forking:
            pool._condition.wait(timeout=0.01)
    assert pool.compress("lz4", b"fallback", False) == independent_compress(
        "lz4", b"fallback", False
    )
    assert not prepared.is_set()
    release.set()
    assert prepared.wait(3)
    finish.set()
    worker.join(3)
    waiter.join(3)
    assert not worker.is_alive() and not waiter.is_alive()
    assert pool.info()["counters"]["fork_fallback"] == 1


def test_quiescence_wait_releases_lock_and_new_work_falls_back():
    script = str(Path(__file__).resolve())
    program = f"import runpy; namespace = runpy.run_path({script!r}); namespace['_quiescence_scenario']()"
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=15,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
@pytest.mark.parametrize("codec", ["lz4", "zstd"])
def test_fork_resets_child_and_parent_remains_usable(codec):
    program = textwrap.dedent("""
        import os, threading
        from benchmarks.compressed_context_lifecycle import ForkSafeSharedContextPool
        from benchmarks.compressed_shared_context import independent_compress
        pool = ForkSafeSharedContextPool(max_contexts=2)
        raw = bytes(range(64))
        expected = pool.compress("lz4", raw, False)
        assert pool.info()["contexts"] == 1
        entered = threading.Event()
        release = threading.Event()
        original = pool._new_context
        def paused(*args):
            entered.set()
            assert release.wait(3)
            return original(*args)
        pool._new_context = paused
        worker = threading.Thread(target=pool.compress, args=("lz4", bytes(range(65)), False))
        worker.start()
        assert entered.wait(3)
        def allow_finish():
            with pool._condition:
                while not pool._forking:
                    pool._condition.wait(timeout=0.01)
            release.set()
        releaser = threading.Thread(target=allow_finish)
        releaser.start()
        child = os.fork()
        if child == 0:
            try:
                assert pool.info()["contexts"] == 0
                assert pool._active == 0 and pool._pid == os.getpid()
                assert pool.compress("lz4", raw, False) == expected
                assert pool.info()["contexts"] == 1
            except BaseException:
                import traceback
                traceback.print_exc()
                os._exit(1)
            os._exit(0)
        worker.join(3)
        releaser.join(3)
        assert not worker.is_alive() and not releaser.is_alive()
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert pool.info()["contexts"] == 2
        assert pool.compress("lz4", raw, False) == expected
    """)
    program = program.replace('"lz4"', repr(codec))
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=15,
        capture_output=True,
        text=True,
    )
