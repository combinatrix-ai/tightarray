"""Fresh-process multistate CA benchmark, exact validation, JSONL progress.

python -m benchmarks.cellpylib_multistate --output docs/results/cellpylib-multistate.jsonl
Warm E2E includes input creation and final materialization; JIT warmup separate.
"""

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time

import cellpylib as cpl
import numba
import numpy as np

from examples.cellpylib_multistate import RULES, rule_callback, simulate


def measure(size, states, rule, backend, mode, steps, repeats):
    full = mode == "history"
    callback = rule_callback(rule, states)

    def run(n):
        a = np.random.default_rng(123).integers(0, states, (n, n), dtype=np.uint8)
        if backend.startswith("upstream"):
            return cpl.evolve2d(
                a[None], steps + 1, callback, memoize=backend == "upstream-memo"
            )
        return simulate(a, steps, states, rule, backend, full_history=full)

    start = time.perf_counter()
    run(8)
    warmup = time.perf_counter() - start
    times = []
    hashes = []
    for _ in range(repeats):
        start = time.perf_counter()
        result = run(size)
        times.append(time.perf_counter() - start)
        hashes.append(hashlib.sha256(result.tobytes()).hexdigest())
        del result
    assert len(set(hashes)) == 1
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    bits = (states - 1).bit_length()
    n = size * size
    payload = (
        2 * ((n * bits + 63) // 64) * 8
        if backend == "packed"
        else 2 * ((n + 64 // bits - 1) // (64 // bits)) * 8
        if backend == "word-aligned"
        else 2 * n
    )
    return {
        "mode": mode,
        "size": size,
        "states": states,
        "rule": rule,
        "backend": backend,
        "steps": steps,
        "warmup_8x8_s": warmup,
        "samples_s": times,
        "median_s": float(np.median(times)),
        "sha256": hashes[0],
        "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "two_buffer_payload_bytes": payload
        if backend in ("dense", "packed", "word-aligned")
        else None,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--worker", nargs=5, metavar=("SIZE", "STATES", "RULE", "BACKEND", "MODE")
    )
    p.add_argument("--output", default="docs/results/cellpylib-multistate.jsonl")
    p.add_argument("--steps", type=int, default=3)
    p.add_argument("--repeats", type=int, default=3)
    args = p.parse_args()
    if args.worker:
        n, k, rule, backend, mode = args.worker
        print(
            json.dumps(
                measure(int(n), int(k), rule, backend, mode, args.steps, args.repeats)
            )
        )
        return
    with open(args.output, "w") as f:
        f.write(
            json.dumps(
                {
                    "environment": {
                        "platform": platform.platform(),
                        "python": platform.python_version(),
                        "numpy": np.__version__,
                        "numba": numba.__version__,
                        "cellpylib": cpl.__version__,
                    }
                }
            )
            + "\n"
        )
        cases = [(64, k, r, "history") for k in (4, 8, 16, 32) for r in RULES]
        cases += [
            (n, k, r, "final")
            for n in (256, 1024, 4096)
            for k in (8, 32)
            for r in RULES
        ]
        cases += [(8192, k, "transport", "final") for k in (8, 32)]
        for n, k, rule, mode in cases:
            backends = ["numpy", "dense", "packed", "word-aligned"]
            if mode == "history":
                backends += ["upstream", "upstream-memo"]
            # Deterministic alternating order avoids always timing packed last.
            if (k + n + RULES.index(rule)) % 2:
                backends.reverse()
            hashes = set()
            for backend in backends:
                command = [
                    sys.executable,
                    "-m",
                    "benchmarks.cellpylib_multistate",
                    "--worker",
                    str(n),
                    str(k),
                    rule,
                    backend,
                    mode,
                    "--steps",
                    str(args.steps),
                    "--repeats",
                    str(args.repeats),
                ]
                result = json.loads(
                    subprocess.check_output(
                        command,
                        text=True,
                        env={**os.environ, "MPLCONFIGDIR": "/tmp/cpl-mpl"},
                    )
                )
                hashes.add(result["sha256"])
                f.write(json.dumps(result) + "\n")
                f.flush()
                print(
                    f"{mode} {n} k={k} {rule} {backend}: {result['median_s']:.5f}s",
                    flush=True,
                )
            assert len(hashes) == 1, (n, k, rule, mode, hashes)


if __name__ == "__main__":
    main()
