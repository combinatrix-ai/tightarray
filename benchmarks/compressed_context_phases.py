"""Measure context reuse in current public update/flush phases."""

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import tightarray.compressed as live
from benchmarks.compressed_bulk_phases import info, make_store, source_guards, write_all
from benchmarks.compressed_hot_bulk import cases, cold_hash, make_trace
from benchmarks.compressed_shared_context import SharedContextPool, memory_study
from benchmarks.compressed_span_bulk_native import sized_trace


def guards():
    result = source_guards()
    for path in (
        Path(__file__),
        Path(__file__).with_name("compressed_shared_context.py"),
    ):
        result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def trial(data, budget, codec, mode, writes, expected):
    pool = SharedContextPool()

    class Shared(live.CompressedArray):
        def _compress(self, raw, *, shuffle):
            return pool.compress(self._codec, raw, shuffle)

    dense = mode == "dense"
    if mode.startswith("shared"):
        array = Shared(data, chunk_size=4096, cache_bytes=budget, codec=codec)
    else:
        array = make_store(data, budget, codec, dense)
    assert array[2048] == int(data[2048])
    if mode == "shared-cold":
        pool.clear()
    before = info(array, dense, budget)
    pool_before = pool.info()
    start = time.perf_counter()
    write_all(array, writes, dense)
    updated = time.perf_counter()
    array.flush()
    flushed = time.perf_counter()
    after = info(array, dense, budget)
    pool_after = pool.info()
    cold = None if dense else cold_hash(array)
    assert array.read(0, len(data)) == expected
    array.clear_cache()
    assert array.read(0, len(data)) == expected
    pool.clear()
    return {
        "updates_ms": (updated - start) * 1000,
        "flush_ms": (flushed - updated) * 1000,
        "total_ms": (flushed - start) * 1000,
        "before": before,
        "after": after,
        "pool_before": pool_before,
        "pool_after": pool_after,
        "cold_sha256": cold,
    }


def run(repeats):
    frozen = guards()
    rng = random.Random(919)
    records = []
    for name, (data, labels) in cases().items():
        for budget in (512, 65536):
            for width in (16, 256):
                trace = sized_trace if name == "span-control" else make_trace
                writes, expected, changes = trace(data, labels, width, count=32)
                for codec in ("lz4", "zstd"):
                    modes = ["adaptive", "dense", "shared-cold", "shared-warm"]
                    samples = {mode: [] for mode in modes}
                    for _ in range(repeats):
                        rng.shuffle(modes)
                        for mode in modes:
                            samples[mode].append(
                                trial(data, budget, codec, mode, writes, expected)
                            )
                    hashes = {
                        s["cold_sha256"]
                        for mode in modes
                        if mode != "dense"
                        for s in samples[mode]
                    }
                    assert len(hashes) == 1
                    records.append(
                        {
                            "case": name,
                            "budget": budget,
                            "width": width,
                            "codec": codec,
                            "changed_values": changes,
                            "samples": samples,
                        }
                    )
    assert frozen == guards()
    return {
        "source_sha256": frozen,
        "repeats": repeats,
        "records": records,
        "scope": "Construction and prewarming excluded. Each trial uses a fresh bounded pool; shared-warm retains constructor contexts, shared-cold clears them before timed writes. Counts include constructor history; pool_before/after separate. RSS excludes neither native contexts nor allocator retention, but array-owned graphs do. Dense helper has less input validation than public API.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=31)
    parser.add_argument("--memory", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("positive repeats required")
    result = memory_study() if args.memory else run(args.repeats)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
