"""Paired current production trim versus pinned pre-trim Python implementation."""

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

import benchmarks.compressed_storage as harness
import tightarray.compressed as live
from benchmarks.compressed_trimmed_endpoints import extra_cases
from benchmarks.compressed_trimmed_policy import (
    guards,
    pinned_baseline,
    retained_graph_bytes,
)

BASELINE = "d6b3746"


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "tightarray").glob("_compressed*.h")) + [
        Path(__file__),
        root / "benchmarks/compressed_trimmed_endpoints.py",
    ]
    for path in paths:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def check_sizes(samples):
    for codec in ("none", "zstd"):
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


def run(size=2**20, repeats=5):
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
            for name, data in extra_cases(size):
                operations = harness.traces(data, 4096)
                methods = [
                    (f"{label}-{codec}", cls, f"palette-{codec}")
                    for label, cls in (("base", base), ("live", original))
                    for codec in ("none", "zstd")
                ] + [
                    ("dense-lz4", base, "dense-lz4"),
                    ("dense-zstd", base, "dense-zstd"),
                ]
                samples = {label: [] for label, _, _ in methods}
                for _ in range(repeats):
                    rng.shuffle(methods)
                    for label, cls, backend in methods:
                        live.CompressedArray = cls
                        samples[label].append(
                            harness.trial(data, backend, 4096, 65536, operations)
                        )
                check_sizes(samples)
                records.append({"case": name, "samples": samples})
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
        "seeds": {"original": 723, "adversarial": 725, "order": 724, "traces": 914},
        "records": records,
        "scope": "Pinned pre-trim Python/current native vs live integrated production, plus dense codecs. Exact operation outputs, all sampled cache bounds and nonincreasing initial/postflush stored payload checked. Shared retained graph accounts for native SpanHot references, excludes runtime state/scratch/allocator overhead, and is not RSS. Each storage phase includes cold+hot graph and trimmed chunk counts when supported.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=2**20)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.size < 4096 or args.size % 4096 or args.repeats < 1:
        parser.error("size must be a positive multiple of 4096; repeats >= 1")
    Path(args.output).write_text(
        json.dumps(run(args.size, args.repeats), indent=2) + "\n"
    )
