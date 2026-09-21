"""Experimental bounded shared scratch contexts; does not change core behavior.

Contexts are keyed by codec, filter, and exact byte length. The metadata lock
covers checkout/return only; busy keys fall back to ordinary compress2 instead
of serializing unrelated arrays. Entries are retained up to a fixed count,
without replacement, avoiding unbounded shape churn. This prototype has no fork
reset hook: workers must create their own pool, and inherited locks/contexts are
not a supported use. Opaque native workspaces
are not part of CompressedArray.storage_info; use fresh-process RSS measurements.
"""

import argparse
import gc
import json
import os
import random
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import blosc2

from benchmarks.compressed_storage import CASES, dataset
from tightarray.compressed import CompressedArray


def parameters(codec, shuffle):
    return {
        "codec": blosc2.Codec.LZ4 if codec == "lz4" else blosc2.Codec.ZSTD,
        "clevel": 5,
        "typesize": 1,
        "nthreads": 1,
        "filters": [blosc2.Filter.BITSHUFFLE if shuffle else blosc2.Filter.NOFILTER],
    }


def independent_compress(codec, raw, shuffle):
    return blosc2.compress2(raw, **parameters(codec, shuffle))


@dataclass
class _Entry:
    context: object = None
    busy: bool = True


class SharedContextPool:
    """Bound live contexts, not undocumented native allocation sizes or RSS."""

    def __init__(self, max_contexts=18, max_payload=4096):
        if max_contexts < 0 or max_payload < 0:
            raise ValueError("Pool bounds must be nonnegative")
        self.max_contexts = max_contexts
        self.max_payload = max_payload
        self._lock = threading.Lock()
        self._entries = {}
        self._counts = Counter()

    def _new_context(self, codec, raw, shuffle):
        return blosc2.SChunk(
            chunksize=len(raw),
            data=raw,
            cparams=parameters(codec, shuffle),
            dparams={"nthreads": 1},
            contiguous=False,
        )

    def compress(self, codec, raw, shuffle):
        key = codec, shuffle, len(raw)
        fallback = None
        with self._lock:
            entry = self._entries.get(key)
            if len(raw) > self.max_payload:
                fallback = "oversize_fallback"
            elif entry is not None and entry.busy:
                fallback = "busy_fallback"
            elif entry is not None:
                entry.busy = True
                self._counts["reuse"] += 1
            elif len(self._entries) >= self.max_contexts:
                fallback = "capacity_fallback"
            else:
                entry = _Entry()
                self._entries[key] = entry
                self._counts["created"] += 1
            if fallback:
                self._counts[fallback] += 1
        if fallback:
            return independent_compress(codec, raw, shuffle)
        try:
            if entry.context is None:
                entry.context = self._new_context(codec, raw, shuffle)
            else:
                entry.context.update_data(0, raw, copy=False)
            value = entry.context.get_chunk(0)
        except BaseException:
            # A failing native operation never returns its mutable context to reuse.
            with self._lock:
                if self._entries.get(key) is entry:
                    del self._entries[key]
                self._counts["dropped_failure"] += 1
            raise
        with self._lock:
            entry.busy = False
        return value

    def info(self):
        with self._lock:
            # Access C-backed payload accounting only on idle contexts.
            contexts = [
                entry.context
                for entry in self._entries.values()
                if not entry.busy and entry.context is not None
            ]
            return {
                "contexts": len(self._entries),
                "busy": sum(e.busy for e in self._entries.values()),
                "max_contexts": self.max_contexts,
                "max_payload": self.max_payload,
                "idle_retained_chunk_bytes": sum(
                    context.cbytes for context in contexts
                ),
                "counters": dict(self._counts),
            }

    def clear(self):
        with self._lock:
            if any(entry.busy for entry in self._entries.values()):
                raise RuntimeError("Cannot clear checked-out contexts")
            self._entries.clear()


@contextmanager
def patched_compression(pool):
    """Process-local benchmark instrumentation, never a production patch API."""
    original = CompressedArray._compress

    def compress(array, raw, *, shuffle):
        return pool.compress(array._codec, raw, shuffle)

    CompressedArray._compress = compress
    try:
        yield
    finally:
        CompressedArray._compress = original


def construct_workload(data, codec, arrays):
    outputs = []
    for _ in range(arrays):
        array = CompressedArray(data, chunk_size=4096, cache_bytes=65536, codec=codec)
        for index in range(0, len(data), max(1, len(data) // 32)):
            array[index] = (data[index] + 17) % 256
        array.flush()
        outputs.append(array)
    return outputs


def timing_study(size=2**20, arrays=4, repeats=3):
    rng = random.Random(267)
    rows = []
    for codec in ("lz4", "zstd"):
        for name in CASES:
            data = dataset(name, size, 4096).tobytes()
            timings = {mode: [] for mode in ("compress2", "shared-cold", "shared-warm")}
            expected_chunks = None
            infos = {}
            for _ in range(repeats):
                order = list(timings)
                rng.shuffle(order)
                for mode in order:
                    pool = SharedContextPool()
                    if mode == "compress2":
                        tick = time.perf_counter()
                        outputs = construct_workload(data, codec, arrays)
                        elapsed = time.perf_counter() - tick
                    else:
                        with patched_compression(pool):
                            if mode == "shared-warm":
                                construct_workload(data, codec, 1)
                            tick = time.perf_counter()
                            outputs = construct_workload(data, codec, arrays)
                            elapsed = time.perf_counter() - tick
                    timings[mode].append(elapsed)
                    chunks = outputs[0]._chunks
                    if expected_chunks is None:
                        expected_chunks = chunks
                    assert chunks == expected_chunks
                    for output in outputs:
                        assert output._chunks == expected_chunks
                    expected = bytearray(data)
                    for index in range(0, len(data), max(1, len(data) // 32)):
                        expected[index] = (data[index] + 17) % 256
                    assert outputs[-1].tobytes() == bytes(expected)
                    infos[mode] = pool.info()
            row = {
                "codec": codec,
                "case": name,
                "arrays": arrays,
                "size": size,
                "seconds": {
                    mode: statistics.median(values) for mode, values in timings.items()
                },
                "samples": timings,
                "pool_info": infos,
                "exact_cold_chunks": True,
            }
            rows.append(row)
            print(row, flush=True)
    return {
        "rows": rows,
        "note": "Full construction + 32 scalar writes + flush per array. Exact cold chunks checked outside timing; pool setup included in shared-cold, excluded in shared-warm. Pool native memory not included in array-owned storage.",
    }


def rss():
    return (
        int(
            subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(os.getpid())], text=True
            ).strip()
        )
        * 1024
    )


def memory_worker(mode, count):
    pool = SharedContextPool()
    rng = random.Random(128)
    inputs = [
        bytes(rng.randrange(1 << bits) for _ in range(4096)) for bits in range(1, 9)
    ]
    gc.collect()
    before = rss()
    outputs = []

    def build():
        for index in range(count):
            codec = ("lz4", "zstd")[(index // 8) % 2]
            outputs.append(
                CompressedArray(
                    inputs[index % 8], chunk_size=4096, cache_bytes=0, codec=codec
                )
            )

    if mode == "shared":
        with patched_compression(pool):
            build()
    else:
        build()
    after = rss()
    result = {
        "mode": mode,
        "arrays": count,
        "rss_before": before,
        "rss_after": after,
        "rss_delta": after - before,
        "pool": pool.info(),
        "array_owned_bytes": sum(array.storage_info().owned_bytes for array in outputs),
        "array_stored_bytes": sum(
            array.storage_info().stored_bytes for array in outputs
        ),
    }
    outputs.clear()
    pool.clear()
    gc.collect()
    result["rss_after_clear"] = rss()
    return result


def memory_study():
    rows = []
    for count in (0, 1, 16, 100, 500):
        for mode in ("compress2", "shared"):
            row = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        "-m",
                        "benchmarks.compressed_shared_context",
                        "--memory-worker",
                        mode,
                        str(count),
                    ],
                    text=True,
                )
            )
            rows.append(row)
            print(row, flush=True)
    return {
        "rows": rows,
        "note": "Separate fresh processes. Current RSS includes allocator/native scratch/runtime effects; pool entries <=18 of payload <=4096. Array-owned bytes exclude shared native contexts.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--size", type=int, default=2**20)
    parser.add_argument("--arrays", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--memory-worker", nargs=2)
    args = parser.parse_args()
    if args.memory_worker:
        print(
            json.dumps(memory_worker(args.memory_worker[0], int(args.memory_worker[1])))
        )
        return
    if not args.output:
        parser.error("--output required")
    result = (
        memory_study()
        if args.memory
        else timing_study(args.size, args.arrays, args.repeats)
    )
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
