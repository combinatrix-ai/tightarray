"""Real CellPyLib Life API, full-history E2E, fresh process per backend/size.

Run: python -m benchmarks.cellpylib_e2e --output docs/results/cellpylib.json
Imports excluded; first call includes JIT. RSS includes imports and JIT.
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

from examples.cellpylib_backend import evolve2d


def worker(backend, size, steps):
    def run():
        # Include deterministic input generation, encoding, updates, and full
        # ndarray history materialization. Every backend gets the same dtype.
        initial = np.random.default_rng(123).integers(
            0, 2, (1, size, size), dtype=np.uint8
        )
        if backend in ("packed", "dense"):
            return evolve2d(initial, steps, cpl.game_of_life_rule, backend=backend)
        memo = {"upstream": False, "memoized": True, "recursive": "recursive"}[backend]
        return cpl.evolve2d(initial, steps, cpl.game_of_life_rule, memoize=memo)

    samples = []
    hashes = []
    for _ in range(4):
        start = time.perf_counter()
        result = run()
        samples.append(time.perf_counter() - start)
        hashes.append(hashlib.sha256(result.tobytes()).hexdigest())
        del result
    assert len(set(hashes)) == 1
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "backend": backend,
        "size": size,
        "steps": steps,
        "first_s": samples[0],
        "warm_s": samples[1:],
        "warm_median_s": float(np.median(samples[1:])),
        "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "history_sha256": hashes[0],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--worker")
    p.add_argument("--size", type=int, default=128)
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--output", default="docs/results/cellpylib.json")
    args = p.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, args.size, args.steps)))
        return
    records = []
    for size in (64, 128):
        for backend in ("upstream", "memoized", "recursive", "dense", "packed"):
            command = [
                sys.executable,
                "-m",
                "benchmarks.cellpylib_e2e",
                "--worker",
                backend,
                "--size",
                str(size),
                "--steps",
                str(args.steps),
            ]
            row = json.loads(
                subprocess.check_output(
                    command,
                    env={**os.environ, "MPLCONFIGDIR": "/tmp/cpl-mpl"},
                    text=True,
                )
            )
            records.append(row)
            print(f"{size} {backend}: {row['warm_median_s']:.6f}s", flush=True)
        assert len({r["history_sha256"] for r in records if r["size"] == size}) == 1
    with open(args.output, "w") as f:
        json.dump(
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "numpy": np.__version__,
                "numba": numba.__version__,
                "cellpylib": cpl.__version__,
                "records": records,
            },
            f,
            indent=2,
        )
        f.write("\n")


if __name__ == "__main__":
    main()
