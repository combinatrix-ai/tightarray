"""Experimental fork-quiescent shared contexts; no production integration.

One process-wide callback trio holds only weak pool registrations. Before fork,
new registrations pause and each pool stops new checkouts while waiting for its
in-flight operations. Condition.wait releases the metadata lock so operations
can finish. Parent unlocks; child replaces locks and drops quiescent contexts.

This covers pool-owned contexts only, not arbitrary concurrent Blosc work.
Fork must originate outside compression callbacks/pool internals. A hung native
operation can delay fork indefinitely; there is no timeout-based unsafe escape.
Opaque codec allocation sizes and allocator RSS retention remain unbounded by
these count limits, exactly as in the original benchmark prototype.
"""

import os
import threading
import weakref
from collections import Counter

from benchmarks.compressed_shared_context import SharedContextPool, independent_compress

_pools = weakref.WeakSet()
_registry_lock = threading.Lock()
_fork_snapshot = []


def _before_fork():
    global _fork_snapshot
    _registry_lock.acquire()
    _fork_snapshot = list(_pools)
    for pool in _fork_snapshot:
        pool._prepare_fork()


def _after_parent():
    global _fork_snapshot
    for pool in reversed(_fork_snapshot):
        pool._finish_parent()
    _fork_snapshot = []
    _registry_lock.release()


def _after_child():
    global _registry_lock, _fork_snapshot
    # Never acquire an inherited lock in the child. Registrations could have
    # been attempted by vanished threads while the parent held the registry gate.
    _registry_lock = threading.Lock()
    for pool in _fork_snapshot:
        pool._reset_child()
    _fork_snapshot = []


if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        before=_before_fork, after_in_parent=_after_parent, after_in_child=_after_child
    )


class ForkSafeSharedContextPool(SharedContextPool):
    """Count-bounded contexts with quiescent fork reset and weak registration."""

    def __init__(self, max_contexts=18, max_payload=4096):
        super().__init__(max_contexts=max_contexts, max_payload=max_payload)
        self._condition = threading.Condition(self._lock)
        self._active = 0
        self._forking = False
        self._pid = os.getpid()
        with _registry_lock:
            _pools.add(self)

    def compress(self, codec, raw, shuffle):
        with self._condition:
            if self._forking:
                self._counts["fork_fallback"] += 1
                fallback = True
            else:
                self._active += 1
                fallback = False
        if fallback:
            # New work cannot prolong quiescence by checking out a pool context.
            # Independent native work is outside the context lifecycle guarantee.
            return independent_compress(codec, raw, shuffle)
        try:
            return super().compress(codec, raw, shuffle)
        finally:
            with self._condition:
                self._active -= 1
                self._condition.notify_all()

    def _prepare_fork(self):
        self._condition.acquire()
        self._forking = True
        while self._active:
            self._condition.wait()
        # Hold this gate across fork; new metadata users cannot race the snapshot.

    def _finish_parent(self):
        self._forking = False
        self._condition.release()

    def _reset_child(self):
        inherited = self._entries
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._entries = {}
        self._counts = Counter()
        self._active = 0
        self._forking = False
        self._pid = os.getpid()
        # Every inherited context was idle before fork, avoiding destruction of
        # workspaces mid-operation in threads that no longer exist in this child.
        inherited.clear()
