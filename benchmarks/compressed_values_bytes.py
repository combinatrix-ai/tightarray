"""Exact-bytes ingestion fast path; isolated paired modules, no live mutations."""

import argparse
import hashlib
import inspect
import json
import random
import statistics
import subprocess
import sys
import time
import types
from contextlib import contextmanager
from pathlib import Path

import tightarray.compressed as live
from tightarray import _core

BASELINE = "ae5c4ff"
MARKER = (
    "    # bytes(int) means allocation, and bytes(buffer) can bypass element checks."
)
INSERTION = "    if type(values) is bytes:\n        return values\n"


def inject(source):
    assert source.count(MARKER) == 1
    if INSERTION + MARKER in source:
        return source
    return source.replace(MARKER, INSERTION + MARKER)


def fast_values():
    namespace = live.__dict__.copy()
    exec(  # noqa: S102
        compile(inject(inspect.getsource(live._values)), "values_candidate", "exec"),
        namespace,
    )
    return namespace["_values"]


@contextmanager
def pair(commit):
    source = subprocess.check_output(
        ["git", "show", f"{commit}:tightarray/compressed.py"],
        cwd=Path(__file__).resolve().parents[1],
    ).decode()
    previous = {}
    modules = {}
    try:
        for key, text in (("baseline", source), ("exact-bytes", inject(source))):
            name = "tightarray._values_trial_" + key.replace("-", "_")
            previous[name] = sys.modules.get(name)
            module = types.ModuleType(name)
            module.__package__ = "tightarray"
            sys.modules[name] = module
            exec(compile(text, name, "exec"), module.__dict__)  # noqa: S102
            modules[key] = module
        yield modules, source
    finally:
        for name, old in previous.items():
            if old is None:
                del sys.modules[name]
            else:
                sys.modules[name] = old


def guards():
    root = Path(__file__).resolve().parents[1]
    paths = [
        Path(__file__),
        Path(_core.__file__),
        root / "tightarray/compressed.py",
        root / "tightarray/_core.c",
        *sorted((root / "tightarray").glob("*.h")),
    ]
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def run(commit=BASELINE, repeats=7, operations=10000):
    before = guards()
    rows = []
    rng = random.Random(314)
    with pair(commit) as (modules, source):
        for size in (1, 16, 64, 256, 4096):
            raw = bytes(range(256)) * (size // 256) + bytes(range(size % 256))
            inputs = {
                "bytes": raw,
                "bytearray": bytearray(raw),
                "memoryview": memoryview(raw),
                "list": list(raw),
            }
            for kind, values in inputs.items():
                samples = {key: [] for key in modules}
                for _ in range(repeats):
                    order = list(modules)
                    rng.shuffle(order)
                    for key in order:
                        fn = modules[key]._values
                        assert fn(values) == raw
                        start = time.perf_counter_ns()
                        for _ in range(operations):
                            result = fn(values)
                        samples[key].append(
                            (time.perf_counter_ns() - start) / operations
                        )
                        assert result == raw
                rows.append(
                    {
                        "operation": "values",
                        "kind": kind,
                        "size": size,
                        "ns_per_operation": samples,
                    }
                )
        # Whole write+flush on warm ordinary direct chunks and cached structural spans.
        for layout in ("ordinary", "span"):
            generator = random.Random(17)
            interior = bytes(
                generator.randrange(32)
                for _ in range(4096 if layout == "ordinary" else 512)
            )
            initial = (
                interior
                if layout == "ordinary"
                else bytes(1792) + interior + bytes(1792)
            )
            for size in (1, 16, 64, 256):
                start_at = 0 if layout == "ordinary" else 1792
                raw = bytes((value + 1) % 32 for value in interior[:size])
                for kind, payload in (
                    ("bytes", raw),
                    ("bytearray", bytearray(raw)),
                    ("memoryview", memoryview(raw)),
                    ("list", list(raw)),
                ):
                    samples = {key: [] for key in modules}
                    expected = bytearray(initial)
                    expected[start_at : start_at + size] = raw
                    for _ in range(repeats):
                        order = list(modules)
                        rng.shuffle(order)
                        for key in order:
                            arr = modules[key].CompressedArray(
                                initial,
                                chunk_size=4096,
                                cache_bytes=65536,
                                codec="none",
                            )
                            arr.read()
                            start = time.perf_counter_ns()
                            for _ in range(256):
                                arr.write(start_at, payload)
                            arr.flush()
                            samples[key].append((time.perf_counter_ns() - start) / 256)
                            assert arr.tobytes() == bytes(expected)
                    rows.append(
                        {
                            "operation": "write-flush",
                            "layout": layout,
                            "kind": kind,
                            "size": size,
                            "ns_per_operation": samples,
                        }
                    )
    assert guards() == before, "source changed during timing"
    return {
        "baseline_commit": commit,
        "baseline_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "source_sha256": before,
        "repeats": repeats,
        "ingestion_operations": operations,
        "writes_per_flush": 256,
        "rows": rows,
        "scope": "Synthetic paired ingestion and 256 repeated writes plus one flush; not app E2E. All fallback code unchanged, only exact built-in bytes bypass buffer copying.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", default=BASELINE)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--operations", type=int, default=10000)
    args = parser.parse_args()
    result = run(args.commit, args.repeats, args.operations)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for row in result["rows"]:
        samples = row["ns_per_operation"]
        print(
            row["operation"],
            row.get("layout", ""),
            row["kind"],
            row["size"],
            {
                key: round(statistics.median(values), 1)
                for key, values in samples.items()
            },
        )
