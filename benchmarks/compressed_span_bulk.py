"""Paired cached partial span bulk writes with a fair chunk-wise dense baseline."""

import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path

import numpy as np

import benchmarks.compressed_storage as harness
import tightarray.compressed as live
from benchmarks.compressed_trimmed_policy import (
    guards,
    pinned_baseline,
    retained_graph_bytes,
)

BASELINE = "6a3ffb2"


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    for path in [Path(__file__), *(root / "tightarray").glob("_compressed*.h")]:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def cases():
    rng = np.random.default_rng(730)
    result = {}
    for bits in (3, 5):
        for palette in (False, True):
            labels = np.arange(
                256 - 2**bits if palette else 0,
                256 if palette else 2**bits,
                dtype=np.uint8,
            )
            span = np.zeros(4096, dtype=np.uint8)
            span[1792:2304] = rng.choice(labels, size=512)
            span[1792] = span[2303] = labels[-1]
            result[f"{'palette' if palette else 'direct'}-{bits}bit"] = (span, labels)
    return result


def trace(data, labels, region):
    rng = np.random.default_rng(731)
    inside = rng.integers(1792, 2304 - 15, size=32)
    outside = rng.integers(0, 1792 - 15, size=32)
    starts = (
        inside
        if region == "inside"
        else outside
        if region == "outside"
        else np.concatenate((inside[:16], outside[:16]))
    )
    expected = bytearray(data.tobytes())
    alphabet = [int(value) for value in labels]
    next_value = {
        value: alphabet[(i + 1) % len(alphabet)] for i, value in enumerate(alphabet)
    }
    writes = []
    changes = 0
    for index in starts:
        old = expected[int(index) : int(index) + 16]
        values = bytes(next_value.get(value, alphabet[0]) for value in old)
        assert all(a != b for a, b in zip(old, values, strict=True))
        expected[int(index) : int(index) + 16] = values
        writes.append((int(index), values))
        changes += sum(a != b for a, b in zip(old, values, strict=True))
    assert changes == 512
    return writes, bytes(expected), changes


def dense_write(array, start, values):
    # Equivalent contiguous byte mutation: decode once per touched chunk, then
    # slice-assign, dirty-cache or encode once. Never benchmark per-byte loops.
    offset = 0
    while offset < len(values):
        key, within = divmod(start, array.chunk)
        count = min(len(values) - offset, array.chunk - within)
        chunk = array.get_chunk(key)
        chunk[within : within + count] = values[offset : offset + count]
        if key in array.cache:
            array.dirty.add(key)
        else:
            array.cold[key] = array.encode(chunk)
        start += count
        offset += count


def trial(cls, backend, data, budget, writes, expected):
    original = live.CompressedArray
    try:
        live.CompressedArray = cls
        store = harness.Store(data, backend, 4096, budget)
    finally:
        live.CompressedArray = original
    # Same scalar prewarm for all methods. Zero/oversized budgets cannot retain
    # the decoded chunk; this is part of the capacity/access tradeoff.
    assert store.data[2048] == int(data[2048])

    def info():
        result = store.info()
        result["owned_bytes"] = retained_graph_bytes(store.data)
        assert result["cache_bytes"] <= budget
        return result

    before = info()
    start = time.perf_counter()
    for index, value in writes:
        if backend.startswith("dense-"):
            dense_write(store.data, index, value)
        else:
            store.data.write(index, value)
    store.flush()
    elapsed = (time.perf_counter() - start) * 1000
    after = info()
    # Check dirty authoritative state, then clear/reload cold storage. Both
    # verifications are outside timing and catch cache-zero lost writes.
    assert store.read(0, 4096) == expected
    store.clear()
    assert store.read(0, 4096) == expected
    reloaded = info()
    return {
        "writes_flush_ms": elapsed,
        "before": before,
        "after": after,
        "reloaded": reloaded,
    }


def run(repeats=5):
    before = source_guards()
    original = live.CompressedArray
    rng, records = random.Random(728), []
    with pinned_baseline(BASELINE) as (base, source):
        for case, (data, labels) in cases().items():
            for budget in (0, 512, 65536):
                for codec in ("none", "zstd"):
                    for region in ("inside", "outside", "mixed"):
                        writes, expected, changes = trace(data, labels, region)
                        methods = [
                            ("base", base, f"palette-{codec}"),
                            ("live", original, f"palette-{codec}"),
                        ]
                        if codec == "zstd":
                            methods.append(("dense-zstd", original, "dense-zstd"))
                        samples = {label: [] for label, _, _ in methods}
                        for _ in range(repeats):
                            rng.shuffle(methods)
                            for label, cls, backend in methods:
                                samples[label].append(
                                    trial(cls, backend, data, budget, writes, expected)
                                )
                        records.append(
                            {
                                "case": case,
                                "cache_bytes": budget,
                                "codec": codec,
                                "region": region,
                                "changed_values": changes,
                                "samples": samples,
                            }
                        )
                print(case, budget, "done", flush=True)
    assert before == source_guards(), "Measured sources changed during benchmark"
    return {
        "baseline_commit": BASELINE,
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "repeats": repeats,
        "seeds": {"data": 730, "trace": 731, "order": 728},
        "records": records,
        "scope": "4096 logical bytes; 512-byte interior in direct/palette3/5bits. 32 partial writes of16bytes,512 real value changes then flush; same scalar prewarm. Dense comparator decodes and byte-slice-assigns once per touched chunk, not scalar-loop emulation. Before/after/reloaded payload/cache/retained graph reported; graph is not RSS. Initial construction and correctness checks excluded. Cold bytes need not match because hot palette history can differ; exact values survive flush/reload including zero or oversized cache. Dense ZSTD uses BITSHUFFLE level5 typesize1 nthreads1.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    result = run(args.repeats)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    for row in result["records"]:
        if row["cache_bytes"] == 512 and row["region"] == "inside":
            print(
                row["cache_bytes"],
                row["codec"],
                row["region"],
                {
                    k: statistics.median(s["writes_flush_ms"] for s in v)
                    for k, v in row["samples"].items()
                },
            )
