"""Compare benchmark-only early native planning with production late native planning."""

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

import benchmarks.compressed_storage as harness
import tightarray.compressed as live
from benchmarks.compressed_trimmed_endpoints import extra_cases
from benchmarks.compressed_trimmed_policy import guards, retained_graph_bytes

BASELINES = {"pretrim": "d6b3746", "early": "c924947"}


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
        root / "benchmarks/compressed_trimmed_endpoints.py",
    ]
    for path in paths:
        result[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def verify_variants(classes, data, operations):
    """Exact cold records before/after common writes; outside timing."""
    for codec in ("none", "zstd"):
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
            reference = arrays["early"]._chunks
            for label in ("native",):
                assert arrays[label]._chunks == reference, (label, codec, mutated)
            assert (
                arrays["native"].storage_info().stored_bytes
                <= arrays["pretrim"].storage_info().stored_bytes
            )


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
            early_python = classes["early"]

            class EarlyNative(early_python):
                def _trim_plan(self, raw, colors, limit):
                    return live._native._trim_plan(raw, colors, bool(self._palette), limit)

            classes["early"] = EarlyNative
            classes["native"] = original
            for name, data in extra_cases(size):
                operations = harness.traces(data, 4096)
                methods = [
                    (f"{label}-{codec}", cls, f"palette-{codec}")
                    for label, cls in classes.items()
                    for codec in ("none", "zstd")
                ] + [("dense-zstd", original, "dense-zstd")]
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
        "baseline_commits": BASELINES,
        "baseline_python_sha256": hashes,
        "source_sha256": before,
        "size": size,
        "repeats": repeats,
        "seeds": {"original": 723, "adversarial": 725, "order": 724, "traces": 914},
        "records": records,
        "scope": "Pinned pretrim Python; pinned early Python encoder overriding only _trim_plan with native helper; live late native planning. Early native has an extra Python wrapper call compared with production direct native invocation. Exact trim-variant cold chunks checked initially and after common writes/flush; nonincreasing payload versus pretrim checked. All operation contents/cache budgets verified. Unified retained object graph is not RSS and excludes codec scratch/shared runtime.",
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
