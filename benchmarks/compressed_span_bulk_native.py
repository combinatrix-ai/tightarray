"""Pinned Python span bulk assignment versus current native bulk assignment.

Reuses the historical 72-configuration workload without changing its files.
Additional inside-only batches use128 real-changing writes of1/16/64/256 bytes.
"""

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

import numpy as np

import tightarray.compressed as live
from benchmarks import compressed_span_bulk as common
from benchmarks.compressed_trimmed_policy import pinned_baseline

BASELINE = "589c0f0"


def guards():
    result = common.source_guards()
    result["benchmarks/compressed_span_bulk_native.py"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    return result


def sized_trace(data, labels, width, count=128):
    rng = np.random.default_rng(732 + width)
    expected = bytearray(data.tobytes())
    alphabet = [int(value) for value in labels]
    next_value = {v: alphabet[(i + 1) % len(alphabet)] for i, v in enumerate(alphabet)}
    writes = []
    changes = 0
    for start in rng.integers(1792, 2304 - width + 1, size=count):
        old = expected[int(start) : int(start) + width]
        value = bytes(next_value[x] for x in old)
        assert all(a != b for a, b in zip(old, value, strict=True))
        writes.append((int(start), value))
        expected[int(start) : int(start) + width] = value
        changes += width
    return writes, bytes(expected), changes


def run(repeats=5, include_matrix=True):
    before = guards()
    original_baseline = common.BASELINE
    records = None
    try:
        common.BASELINE = BASELINE
        if include_matrix:
            records = common.run(repeats)
    finally:
        common.BASELINE = original_baseline
    rows = []
    rng = random.Random(733)
    with pinned_baseline(BASELINE) as (base, source):
        for name, (data, labels) in common.cases().items():
            for width in (1, 16, 64, 256):
                writes, expected, changed = sized_trace(data, labels, width)
                for budget in (512, 65536):
                    for codec in ("none", "zstd"):
                        methods = [
                            ("base", base, f"palette-{codec}"),
                            ("live", live.CompressedArray, f"palette-{codec}"),
                        ]
                        if codec == "zstd":
                            methods.append(
                                ("dense-zstd", live.CompressedArray, "dense-zstd")
                            )
                        samples = {name: [] for name, _, _ in methods}
                        for _ in range(repeats):
                            rng.shuffle(methods)
                            for label, cls, backend in methods:
                                samples[label].append(
                                    common.trial(
                                        cls, backend, data, budget, writes, expected
                                    )
                                )
                        rows.append(
                            {
                                "case": name,
                                "write_bytes": width,
                                "write_count": len(writes),
                                "changed_values": changed,
                                "cache_bytes": budget,
                                "codec": codec,
                                "samples": samples,
                            }
                        )
                print(name, width, "complete", flush=True)
    assert before == guards(), "Measured sources changed during benchmark"
    return {
        "baseline_commit": BASELINE,
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "repeats": repeats,
        "matrix": records,
        "size_records": rows,
        "scope": "Pinned589c0f0 Python span view assignment with current native binary vs live native span bulk path. Historical72-config workload reused; extra128-write inside batches of1/16/64/256bytes, all actual changes. Construction excluded; writes+flush timed. Full values/cache/flushreload checked by common trial. Before/after/reloaded graph includes hot native references, excludes scratch/shared runtime and is not RSS. Dense chunk-slice helper receives prevalidated bytes and lacks complete public API validation. Exact cold byte identity not required.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sizes-only", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    result = run(args.repeats, not args.sizes_only)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    for row in result["size_records"]:
        if row["cache_bytes"] == 512 and row["codec"] == "none":
            print(
                row["case"],
                row["write_bytes"],
                {
                    k: statistics.median(x["writes_flush_ms"] for x in v)
                    for k, v in row["samples"].items()
                },
            )
