"""Method-level time and memory comparisons; run with python benchmarks/run.py."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import timeit
import tracemalloc

import numpy as np
from tightarray import Array, Matrix, RaggedArray


def deep_size(obj, seen=None):
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return 0
    seen.add(id(obj))
    size = sys.getsizeof(obj)
    if isinstance(obj, (list, tuple)):
        size += sum(deep_size(x, seen) for x in obj)
    elif isinstance(obj, Array) and obj.base is not None:
        size += deep_size(obj.base, seen)
    elif isinstance(obj, np.ndarray) and obj.base is not None:
        size += deep_size(obj.base, seen)
    return size


def measure(fn, repeats, target):
    timer = timeit.Timer(fn)
    number = 1
    while timer.timeit(number) < target and number < 1_000_000:
        number *= 2
    samples = [timer.timeit(number) / number for _ in range(repeats)]
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    result = fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(ns_op=statistics.median(samples) * 1e9,
                min_ns_op=min(samples) * 1e9, max_ns_op=max(samples) * 1e9,
                additional_peak_bytes=max(0, peak - before), result_retained_bytes=deep_size(result),
                loops=number, samples_ns=[s * 1e9 for s in samples])


def run_1d(bits, n):
    rng = random.Random(41 + bits + n)
    src = bytes(rng.randrange(1 << bits) for _ in range(n))
    idx = n // 2
    indices = [rng.randrange(n) for _ in range(min(256, n))]
    npindices = np.array(indices, dtype=np.intp)
    lo, hi = n // 4, n * 3 // 4
    value = (1 << bits) - 1
    needle = bytes([value]) * 8  # Usually absent; reference checks do not assume that.
    factories = {
        "python-list": lambda: list(src),
        "python-bytes": lambda: bytes(bytearray(src)),
        "python-str": lambda: src.decode("latin1"),
        "numpy": lambda: np.frombuffer(src, dtype=np.uint8).copy(),
        "packed": lambda: Array(src, bits=bits, layout="packed"),
        "word-aligned": lambda: Array(src, bits=bits, layout="word-aligned"),
    }
    for name, factory in factories.items():
        data, other = factory(), factory()
        operations = {"construct": factory, "get": lambda d=data: d[idx],
                      "slice-copy": lambda d=data: d[lo:hi],
                      "gather": lambda d=data: [d[i] for i in indices],
                      "iterate-sum": lambda d=data: sum(d),
                      "equal": lambda d=data, o=other: d == o,
                      "count": lambda d=data: d.count(value)}
        if name == "python-list":
            operations["find"] = lambda d=data: bytes(d).find(needle)
        elif name == "python-bytes":
            operations["find"] = lambda d=data: d.find(needle)
        elif name == "python-str":
            operations["get"] = lambda d=data: ord(d[idx])
            operations["gather"] = lambda d=data: [ord(d[i]) for i in indices]
            operations["iterate-sum"] = lambda d=data: sum(map(ord, d))
            operations["count"] = lambda d=data: d.count(chr(value))
            operations["find"] = lambda d=data: d.find(needle.decode("latin1"))
        elif name == "numpy":
            operations["slice-view"] = lambda d=data: d[lo:hi]
            operations["slice-copy"] = lambda d=data: d[lo:hi].copy()
            operations["gather"] = lambda d=data: d[npindices]
            operations["equal"] = lambda d=data, o=other: np.array_equal(d, o)
            operations["count"] = lambda d=data: np.count_nonzero(d == value)
            operations["iterate-sum"] = lambda d=data: sum(map(int, d))
            operations["find"] = lambda d=data: d.tobytes().find(needle)
        else:
            operations["slice-view"] = lambda d=data: d[lo:hi]
            operations["slice-copy"] = lambda d=data: d[lo:hi].copy()
            operations["gather"] = lambda d=data: d.gather(indices)
            operations["find"] = lambda d=data: d.find(needle)
        if name not in ("python-bytes", "python-str"):
            def setter(d=data):
                d[idx] = src[idx]
            operations["set"] = setter
        expected = {"get": src[idx], "iterate-sum": sum(src), "equal": True,
                    "count": src.count(value), "find": src.find(needle)}
        for method, fn in operations.items():
            result = fn()
            if method in expected:
                assert result == expected[method], (name, method, result, expected[method])
            elif method in ("construct", "slice-copy", "slice-view", "gather"):
                actual = list(map(ord, result)) if isinstance(result, str) else list(result)
                ref = list(src) if method == "construct" else [src[i] for i in indices] if method == "gather" else list(src[lo:hi])
                assert actual == ref
            yield dict(structure="1d", bits=bits, elements=n, implementation=name,
                       method=method, dataset_retained_bytes=deep_size(data)), fn


def run_nested(bits, n, ragged):
    rng = random.Random(971 + bits + n)
    rows, left = [], n
    while left:
        length = min(left, rng.randrange(1, 129) if ragged else 64)
        rows.append([rng.randrange(1 << bits) for _ in range(length)])
        left -= length
    if ragged:
        rows.insert(0, [])
    kind = RaggedArray if ragged else Matrix
    flat = np.array([x for row in rows for x in row], dtype=np.uint8)
    offsets = np.concatenate(([0], np.cumsum([len(r) for r in rows], dtype=np.uint64))).astype(np.uint64)
    r = len(rows) // 2
    value = (1 << bits) - 1
    for name in ("python-list", "numpy", "packed", "word-aligned"):
        if name == "python-list":
            factory = lambda: [list(row) for row in rows]
            data = factory()
            ops = {"get": lambda: data[r][0], "row-copy": lambda: data[r][:],
                   "count": lambda: sum(row.count(value) for row in data),
                   "equal": lambda other=factory(): data == other}
            def setter():
                data[r][0] = rows[r][0]
        elif name == "numpy":
            factory = (lambda: (flat.copy(), offsets.copy())) if ragged else (lambda: flat.reshape(-1, 64).copy())
            data = factory()
            def row():
                return data[0][int(data[1][r]):int(data[1][r + 1])] if ragged else data[r]
            ops = {"get": lambda: data[0][int(data[1][r])] if ragged else data[r, 0],
                   "row-copy": lambda: row().copy(), "row-view": row,
                   "count": lambda: np.count_nonzero((data[0] if ragged else data) == value),
                   "equal": lambda other=factory(): all(np.array_equal(a, b) for a, b in zip(data, other)) if ragged else np.array_equal(data, other)}
            def setter():
                if ragged:
                    data[0][int(data[1][r])] = rows[r][0]
                else:
                    data[r, 0] = rows[r][0]
        else:
            factory = lambda: kind(rows, bits=bits, layout=name)
            data = factory()
            ops = {"get": lambda: data[r, 0], "row-copy": lambda: data[r].copy(),
                   "row-view": lambda: data[r], "count": lambda: data.count(value),
                   "equal": lambda other=factory(): data == other}
            def setter():
                data[r, 0] = rows[r][0]
        ops.update(construct=factory, set=setter)
        for method, fn in ops.items():
            result = fn()
            if method == "get":
                assert result == rows[r][0]
            elif method == "count":
                assert result == sum(row.count(value) for row in rows)
            elif method == "equal":
                assert result
            elif method.startswith("row-"):
                assert list(result) == rows[r]
            yield dict(structure="ragged" if ragged else "matrix", bits=bits, elements=n,
                       implementation=name, method=method, dataset_retained_bytes=deep_size(data)), fn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1024, 65536])
    parser.add_argument("--bits", type=int, nargs="+", default=[2, 5, 7])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--target", type=float, default=.005)
    parser.add_argument("--only-1d", action="store_true")
    args = parser.parse_args()
    if any(n < 64 or n % 64 for n in args.sizes):
        parser.error("sizes must be positive multiples of 64")
    meta = dict(python=sys.version, numpy=np.__version__, platform=platform.platform(),
                machine=platform.machine(), compiler=platform.python_compiler(),
                load_before=os.getloadavg(), seed="deterministic per case",
                peak_method="tracemalloc: includes PyMem and NumPy-tracked buffers; excludes untracked system allocations",
                timing="median of adaptive batches; GC disabled during timing; no CPU affinity",
                find_baseline="Python list and NumPy include conversion to bytes; bytes/str use native find",
                source_sha256=hashlib.sha256(Path(__file__).parents[1].joinpath("tightarray/_core.c").read_bytes()).hexdigest())
    if sys.platform == "darwin":
        meta["cpu"] = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    results = []
    for bits in args.bits:
        for n in args.sizes:
            streams = [run_1d(bits, n)]
            if not args.only_1d:
                streams += [run_nested(bits, n, False), run_nested(bits, n, True)]
            for stream in streams:
                for info, fn in stream:
                    info.update(measure(fn, args.repeats, args.target))
                    info["ns_element"] = info["ns_op"] / n if info["method"] in ("construct", "count", "iterate-sum", "equal", "find") else None
                    results.append(info)
            print(f"finished bits={bits} n={n}", flush=True)
    meta["load_after"] = os.getloadavg()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(metadata=meta, results=results), indent=2) + "\n")


if __name__ == "__main__":
    main()
