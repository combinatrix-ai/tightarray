"""Measure exact minimum-header pruning against its pinned predecessor."""

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import numpy as np

import benchmarks.compressed_storage as harness
import tightarray.compressed as live
from benchmarks.compressed_codec_policy import extras
from benchmarks.compressed_trimmed_policy import guards, retained_graph_bytes

BASELINES = {"base": "d90c7dd"}


@contextmanager
def baselines():
    root = Path(__file__).resolve().parents[1]
    classes, hashes, modules = {}, {}, []
    try:
        for label, commit in BASELINES.items():
            source = subprocess.check_output(
                ["git", "show", f"{commit}:tightarray/compressed.py"], cwd=root
            )
            name = f"tightarray._planning_{label}"
            module = types.ModuleType(name)
            module.__package__ = "tightarray"
            sys.modules[name] = module
            modules.append(name)
            exec(compile(source, f"pinned_{label}.py", "exec"), module.__dict__)  # noqa: S102
            classes[label] = module.CompressedArray
            hashes[label] = hashlib.sha256(source).hexdigest()
        yield classes, hashes
    finally:
        for name in modules:
            del sys.modules[name]


def source_guards():
    result = guards()
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "tightarray").glob("_compressed*.h")) + [
        Path(__file__),
        root / "benchmarks/compressed_codec_policy.py",
    ]
    for path in paths:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def verify_variants(classes, data, operations):
    """Exact cold records before/after common writes; outside timing."""
    for codec in ("none", "lz4", "zstd"):
        arrays = {
            label: cls(data.tobytes(), chunk_size=4096, cache_bytes=65536, codec=codec)
            for label, cls in classes.items()
        }
        for mutated in (False, True):
            if mutated:
                for array in arrays.values():
                    for index, value in zip(
                        operations[-2], operations[-1], strict=True
                    ):
                        array[index] = value
                    array.flush()
            reference = arrays["base"]._chunks
            for label in ("native",):
                assert arrays[label]._chunks == reference, (label, codec, mutated)
            assert (
                arrays["native"].storage_info().stored_bytes
                <= arrays["base"].storage_info().stored_bytes
            )


def all_cases(size):
    for name in harness.CASES:
        yield name, harness.dataset(name, size, 4096)
    yield from extras(size, 4096, True)
    yield "two-period-direct", np.resize(np.array([0, 1], dtype=np.uint8), size)
    yield "two-period-high", np.resize(np.array([200, 255], dtype=np.uint8), size)


def count_calls(cls, data, operations, codec):
    calls = 0

    class Counted(cls):
        def _compress(self, raw, *, shuffle):
            nonlocal calls
            calls += 1
            return super()._compress(raw, shuffle=shuffle)

    array = Counted(data.tobytes(), chunk_size=4096, cache_bytes=65536, codec=codec)
    build_calls = calls
    for index, value in zip(operations[-2], operations[-1], strict=True):
        array[index] = value
    array.flush()
    return {"construction": build_calls, "updates_flush": calls - build_calls}


def run(size=2**20, repeats=5):
    before = source_guards()
    original, original_info = live.CompressedArray, harness.Store.info
    rng, records = random.Random(724), []

    def graph_info(store):
        info = original_info(store)
        info["owned_bytes"] = retained_graph_bytes(store.data)
        return info

    try:
        harness.Store.info = graph_info
        with baselines() as (classes, hashes):
            classes["native"] = original
            for name, data in all_cases(size):
                operations = harness.traces(data, 4096)
                methods = [
                    (f"{label}-{codec}", cls, f"palette-{codec}")
                    for label, cls in classes.items()
                    for codec in ("none", "lz4", "zstd")
                ]
                samples = {label: [] for label, _, _ in methods}
                for _ in range(repeats):
                    rng.shuffle(methods)
                    for label, cls, backend in methods:
                        live.CompressedArray = cls
                        sample = harness.trial(data, backend, 4096, 65536, operations)
                        for key, info in sample.items():
                            if key.endswith("storage"):
                                assert info["cache_bytes"] <= info.get(
                                    "cache_limit_bytes", 65536
                                )
                        samples[label].append(sample)
                verify_variants(classes, data, operations)
                counts = {
                    f"{label}-{codec}": count_calls(cls, data, operations, codec)
                    for label, cls in classes.items()
                    for codec in ("none", "lz4", "zstd")
                }
                records.append(
                    {"case": name, "samples": samples, "compress_calls": counts}
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
        "baseline_commits": BASELINES,
        "baseline_python_sha256": hashes,
        "source_sha256": before,
        "size": size,
        "repeats": repeats,
        "seeds": {"dataset": 812, "adverse": 681, "order": 724, "traces": 914},
        "records": records,
        "scope": "Pinned d90c7dd Python/current native vs live header pruning; none/LZ4/ZSTD. Exact cold records initially and after updates/flush; decoded contents/cache bounds checked. Compression call counters are a separate untimed pass. Retained graph is not RSS and excludes runtime/scratch. MIN_HEADER_LENGTH lower bound only; no compression-quality heuristic.",
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
