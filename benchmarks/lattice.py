"""Run from repository root: python -m benchmarks.lattice --output result.json."""

import argparse
import hashlib
import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path

import numba
import numpy as np

from examples.lattice import PackedGrid, evolve_dense_into, evolve_numpy_into


def measure(size, states, steps, repeats):
    initial = np.random.default_rng(20260919).integers(
        0, states, (size, size), dtype=np.uint8
    )
    expected, scratch = initial.copy(), np.empty_like(initial)
    evolve_numpy_into(expected, scratch, states, steps)
    expected = (scratch if steps % 2 else expected).copy()
    backends = {}
    for name in ["numpy", "numba-numpy", "numba-packed", "numba-aligned"]:
        if name.startswith("numba-") and name not in ("numba-numpy",):
            grid = PackedGrid(
                initial,
                states=states,
                layout="packed" if name == "numba-packed" else "word-aligned",
            )
            # Restore both descriptor/owner order through constructing once per trial;
            # construction is outside update timings and measured separately below.
            backends[name] = {
                "payload_bytes": grid.nbytes,
                "samples_s": [],
                "construction_s": [],
                "materialize_s": [],
            }
            grid.step(1)  # Excludes first-call compilation.
        else:
            backends[name] = {
                "payload_bytes": initial.nbytes * 2,
                "samples_s": [],
                "construction_s": [],
                "materialize_s": [],
            }
            if name == "numba-numpy":
                evolve_dense_into(
                    initial.copy().ravel(),
                    np.empty(initial.size, dtype=np.uint8),
                    size,
                    size,
                    states,
                    1,
                )
    for repeat in range(repeats):
        for name in list(backends)[:: 1 if repeat % 2 == 0 else -1]:
            start = time.perf_counter()
            if name in ("numba-packed", "numba-aligned"):
                grid = PackedGrid(
                    initial,
                    states=states,
                    layout="packed" if name == "numba-packed" else "word-aligned",
                )
                build_time = time.perf_counter() - start
                start = time.perf_counter()
                grid.step(steps)
                elapsed = time.perf_counter() - start
                start = time.perf_counter()
                actual = grid.to_numpy()
                materialize = time.perf_counter() - start
            else:
                a, b = initial.copy(), np.empty_like(initial)
                build_time = time.perf_counter() - start
                start = time.perf_counter()
                if name == "numpy":
                    evolve_numpy_into(a, b, states, steps)
                else:
                    evolve_dense_into(a.ravel(), b.ravel(), size, size, states, steps)
                elapsed = time.perf_counter() - start
                actual = b if steps % 2 else a
                materialize = 0.0  # Already a logical uint8 grid.
            np.testing.assert_array_equal(actual, expected)
            backends[name]["samples_s"].append(elapsed)
            backends[name]["construction_s"].append(build_time)
            backends[name]["materialize_s"].append(materialize)
    for name, result in backends.items():
        result["median_s"] = statistics.median(result["samples_s"])
        result["median_construction_s"] = statistics.median(result["construction_s"])
        result["median_materialize_s"] = statistics.median(result["materialize_s"])
        if name in ("numba-packed", "numba-aligned"):
            grid = PackedGrid(
                initial,
                states=states,
                layout="packed" if name == "numba-packed" else "word-aligned",
            )
            tracemalloc.start()
            grid.step(steps)
        else:
            a, b = initial.copy(), np.empty_like(initial)
            tracemalloc.start()
            if name == "numpy":
                evolve_numpy_into(a, b, states, steps)
            else:
                evolve_dense_into(a.ravel(), b.ravel(), size, size, states, steps)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result["traced_update_peak_bytes"] = peak
    return {
        "size": size,
        "states": states,
        "steps": steps,
        "output_sha256": hashlib.sha256(expected.tobytes()).hexdigest(),
        "backends": backends,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[128, 512, 1024])
    parser.add_argument("--states", type=int, nargs="+", default=[2, 4, 8])
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        min(args.sizes) < 1
        or min(args.states) < 2
        or max(args.states) > 256
        or args.steps < 1
        or args.repeats < 1
    ):
        parser.error("positive sizes/steps/repeats and states in 2..256 required")
    result = {
        "python": platform.python_version(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "numba": numba.__version__,
        "method": "fixed seed, JIT warmup excluded, alternating order, every output checked against NumPy; construction and materialization timed separately; two-grid payload excludes Python/JIT metadata; separate tracemalloc pass is not RSS",
        "cases": [],
    }
    for size in args.sizes:
        for states in args.states:
            case = measure(size, states, args.steps, args.repeats)
            result["cases"].append(case)
            print(
                size,
                states,
                {
                    name: round(value["median_s"] * 1000, 3)
                    for name, value in case["backends"].items()
                },
                flush=True,
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
