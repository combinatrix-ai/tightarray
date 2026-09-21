"""Compare full operations with Python versus native modal-span recognition.

The exhaustive baseline encode and span palette/packing work remain unchanged.
This is a benchmark-only candidate, not a production implementation. Historical
trimmed-policy results are preserved separately; this run records fresh hashes.
"""

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

import benchmarks.compressed_storage as harness
import tightarray.compressed as live
from benchmarks.compressed_trimmed_policy import (
    BASELINE_COMMIT,
    cases,
    guards,
    pinned_baseline,
    retained_graph_bytes,
    trimmed_class,
)


def source_guards():
    result = guards()
    result["benchmarks/compressed_trimmed_recognition.py"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    result["tightarray/_compressed_trim.h"] = hashlib.sha256(
        (Path(__file__).resolve().parents[1] / "tightarray/_compressed_trim.h").read_bytes()
    ).hexdigest()
    return result


def run(size=2**20, repeats=5):
    before = source_guards()
    rng = random.Random(724)
    records = []
    original = live.CompressedArray
    original_info = harness.Store.info

    def graph_info(store):
        result = original_info(store)
        result["owned_bytes"] = retained_graph_bytes(store.data)
        return result

    try:
        harness.Store.info = graph_info
        with pinned_baseline() as (base, source):
            python_trim = trimmed_class(base)
            native_trim = trimmed_class(base, live._native._byte_trim)
            for name, data in cases(size):
                operations = harness.traces(data, 4096)
                methods = [
                    (f"{label}-{codec}", cls, f"palette-{codec}")
                    for label, cls in (
                        ("base", base), ("python", python_trim), ("native", native_trim)
                    )
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
                # Both recognizers must select identical exact payloads, not just
                # agree on decoded values. Verification is outside timing.
                for codec in ("none", "zstd"):
                    a = python_trim(data.tobytes(), chunk_size=4096, codec=codec)
                    b = native_trim(data.tobytes(), chunk_size=4096, codec=codec)
                    assert a._chunks == b._chunks
                records.append({"case": name, "samples": samples})
                print(name, {
                    label: statistics.median(s["build_ms"] for s in rows)
                    for label, rows in samples.items()
                }, flush=True)
    finally:
        live.CompressedArray = original
        harness.Store.info = original_info
    assert before == source_guards(), "Measured sources changed during benchmark"
    return {
        "baseline_commit": BASELINE_COMMIT,
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "size": size, "repeats": repeats, "seed": 723,
        "records": records,
        "scope": (
            "Pinned Python baseline with current native extension. Only modal span "
            "recognition differs between python/native variants; exhaustive original "
            "encoding, duplicate palette scans, Python structural hot access and "
            "mutation expansion remain. Unified reachable graph accounting, not RSS. "
            "All operation contents and Python/native cold payload equality checked."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=2**20)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.size < 4096 or args.size % 4096 or args.repeats < 1:
        parser.error("size must be a positive multiple of 4096; repeats >= 1")
    Path(args.output).write_text(json.dumps(run(args.size, args.repeats), indent=2) + "\n")
