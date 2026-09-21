"""Bounded actual-change span writes across cache budgets and access regions."""

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

BASELINE = "5defad8"


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    for path in [Path(__file__), *(root / "tightarray").glob("_compressed*.h")]:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def cases():
    rng = np.random.default_rng(726)
    span = np.zeros(4096, dtype=np.uint8)
    span[1792:2304] = rng.integers(32, size=512, dtype=np.uint8)
    span[1792] = span[2303] = 31
    return {
        "span512": span,
        "random-control": rng.integers(32, size=4096, dtype=np.uint8),
        "periodic-control": np.tile(np.arange(32, dtype=np.uint8), 128),
    }


def trace(data, region):
    rng = np.random.default_rng(727)
    inside = rng.choice(np.arange(1792, 2304), 64, replace=False)
    outside = rng.choice(
        np.concatenate((np.arange(1792), np.arange(2304, 4096))), 64, replace=False
    )
    indices = (
        inside
        if region == "inside"
        else outside
        if region == "outside"
        else np.concatenate((inside[:32], outside[:32]))
    )
    expected = data.copy()
    writes = []
    for index in indices:
        value = (int(expected[index]) + 1) % 32
        assert value != int(expected[index])
        writes.append((int(index), value))
        expected[index] = value
    return writes, expected.tobytes()


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
        store.data[index] = value
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
        for case, data in cases().items():
            for budget in (0, 512, 65536):
                for codec in ("none", "zstd"):
                    for region in ("inside", "outside", "mixed"):
                        writes, expected = trace(data, region)
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
        "seeds": {"data": 726, "trace": 727, "order": 728},
        "records": records,
        "scope": "4096 logical bytes; span interior [1792:2304] packed320 bytes. 64 actual changed assignments within logical0..31 then flush; same scalar prewarm. Before/after/reloaded payload/cache/retained graph reported; graph is not RSS. Initial construction and correctness checks excluded. Cold bytes need not match because hot palette history can differ; exact values survive flush/reload including zero or oversized cache. Dense ZSTD uses BITSHUFFLE level5 typesize1 nthreads1.",
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
        if row["case"] == "span512":
            print(
                row["cache_bytes"],
                row["codec"],
                row["region"],
                {
                    k: statistics.median(s["writes_flush_ms"] for s in v)
                    for k, v in row["samples"].items()
                },
            )
