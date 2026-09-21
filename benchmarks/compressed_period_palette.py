"""Paired periodic pattern palette minimization versus previous encoder."""

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

import numpy as np

import benchmarks.compressed_storage as harness
import tightarray.compressed as live
from benchmarks.compressed_trimmed_policy import (
    guards,
    pinned_baseline,
    retained_graph_bytes,
)

BASELINE = "4857c2a"


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "tightarray").glob("_compressed*.h")) + [
        Path(__file__),
    ]
    for path in paths:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def check_sizes(samples):
    for codec in ("none", "lz4", "zstd"):
        for before, after in zip(
            samples[f"base-{codec}"], samples[f"live-{codec}"], strict=True
        ):
            for phase in ("initial_storage", "updated_storage"):
                assert after[phase]["stored_bytes"] <= before[phase]["stored_bytes"], (
                    codec,
                    phase,
                )
    for rows in samples.values():
        for sample in rows:
            for key, info in sample.items():
                if key.endswith("storage"):
                    assert info["cache_bytes"] <= info.get("cache_limit_bytes", 65536)


def fixtures(size):
    # size=1MiB means256 chunks, preserving each original test's chunk length.
    copies = max(1, size // 4096)
    patterns = (
        ("high32-period32", bytes(range(224, 256)), 128),
        ("high-two-period2", bytes([200, 255]), 2048),
        ("high-two-period31", bytes([200]) * 30 + bytes([255]), 128),
        ("tiny-high-period2", bytes([200, 255]), 5),
        ("low-period31-control", bytes(range(31)), 128),
    )
    for name, pattern, repeats in patterns:
        raw = pattern * repeats
        yield name, np.frombuffer(raw * copies, dtype=np.uint8), len(raw)
    rng = np.random.default_rng(729)
    yield "random32-control", rng.integers(32, size=copies * 4096, dtype=np.uint8), 4096
    broken = bytearray(bytes(range(224, 256)) * 128)
    broken[-1] = 0
    yield (
        "late-mismatch-control",
        np.frombuffer(bytes(broken) * copies, dtype=np.uint8),
        4096,
    )


def run(size=2**20, repeats=5):
    if size < 32768 or size % 4096 or repeats < 1:
        raise ValueError("size must be a multiple of 4096 >=32768, repeats positive")
    before = source_guards()
    rng = random.Random(724)
    original, original_info = live.CompressedArray, harness.Store.info
    records = []

    def graph_info(store):
        info = original_info(store)
        info["owned_bytes"] = retained_graph_bytes(store.data)
        return info

    try:
        harness.Store.info = graph_info
        with pinned_baseline(BASELINE) as (base, source):
            for name, data, chunk in fixtures(size):
                operations = harness.traces(data, chunk)
                methods = [
                    (f"{label}-{codec}", cls, f"palette-{codec}")
                    for label, cls in (("base", base), ("live", original))
                    for codec in ("none", "lz4", "zstd")
                ]
                samples = {label: [] for label, _, _ in methods}
                for _ in range(repeats):
                    rng.shuffle(methods)
                    for label, cls, backend in methods:
                        live.CompressedArray = cls
                        samples[label].append(
                            harness.trial(data, backend, chunk, 65536, operations)
                        )
                check_sizes(samples)
                records.append(
                    {
                        "case": name,
                        "chunk_size": chunk,
                        "logical_bytes": len(data),
                        "samples": samples,
                    }
                )
                print(
                    name,
                    {
                        label: statistics.median(s["build_ms"] for s in rows)
                        for label, rows in samples.items()
                    },
                    flush=True,
                )
    finally:
        live.CompressedArray, harness.Store.info = original, original_info
    assert before == source_guards(), "Measured sources changed during benchmark"
    return {
        "baseline_commit": BASELINE,
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "size": size,
        "repeats": repeats,
        "seeds": {"control": 729, "order": 724, "traces": 914},
        "records": records,
        "scope": "Pinned4857c2a Python/current native vs live periodic palette minimization. Four exact unit-test pattern/repeat/chunk fixtures repeated up to256chunks plus controls. Records intentionally differ; exact logical operation outputs, cache bounds and nonincreasing payload checked. Retained graph includes metadata and hot references, excludes runtime/scratch; not RSS. Updates may include no-ops.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=2**20)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.size < 32768 or args.size % 4096 or args.repeats < 1:
        parser.error("size must be a multiple of 4096 >=32768; repeats >= 1")
    Path(args.output).write_text(
        json.dumps(run(args.size, args.repeats), indent=2) + "\n"
    )
