"""Fixed observed RSS budget; fresh process per trial; report tested frontier."""

import argparse
import json
import platform
import subprocess
import sys
import time

import numba
import numpy as np

from examples.capacity_grid import CapacityGrid, peak_bytes, update_row


def trial(size, states, backend, budget, steps):
    result = {
        "size": size,
        "cells": size * size,
        "states": states,
        "backend": backend,
        "budget_bytes": budget,
        "steps": steps,
    }
    start = time.perf_counter()
    small = np.zeros(8, dtype=np.uint8)
    update_row(small, small, small, small.copy(), states)
    result["jit_s"] = time.perf_counter() - start
    result["baseline_peak_bytes"] = peak_bytes()
    start = time.perf_counter()
    try:
        grid = CapacityGrid(size, size, states, backend, budget=budget)
        result["init_s"] = time.perf_counter() - start
        result["payload_bytes"] = grid.payload_bytes
        times = []
        for _ in range(steps):
            tick = time.perf_counter()
            grid.step()
            times.append(time.perf_counter() - tick)
        result["step_s"] = times
        tick = time.perf_counter()
        result.update(grid.digest())
        result["digest_s"] = time.perf_counter() - tick
        result["status"] = "completed"
    except MemoryError:
        result["status"] = "over_budget"
    result["e2e_s"] = time.perf_counter() - start
    result["peak_bytes"] = peak_bytes()
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--worker", nargs=3)
    p.add_argument("--budget-mib", type=int, default=512)
    p.add_argument("--steps", type=int, default=3)
    p.add_argument("--output", default="docs/results/capacity-grid.jsonl")
    args = p.parse_args()
    if args.worker:
        n, k, backend = args.worker
        print(
            json.dumps(
                trial(int(n), int(k), backend, args.budget_mib * 2**20, args.steps)
            )
        )
        return
    with open(args.output, "w") as f:
        f.write(
            json.dumps(
                {
                    "environment": {
                        "python": platform.python_version(),
                        "platform": platform.platform(),
                        "numpy": np.__version__,
                        "numba": numba.__version__,
                    }
                }
            )
            + "\n"
        )

        def run(n, k, backend):
            command = [
                sys.executable,
                "-m",
                "benchmarks.capacity_grid",
                "--worker",
                str(n),
                str(k),
                backend,
                "--budget-mib",
                str(args.budget_mib),
                "--steps",
                str(args.steps),
            ]
            row = json.loads(subprocess.check_output(command, text=True))
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(
                n,
                k,
                backend,
                row["status"],
                round(row["peak_bytes"] / 2**20, 1),
                flush=True,
            )
            return row

        for k in (8, 32):
            # Equal-size validation without retaining dense reference in packed process.
            a, b = run(8192, k, "dense"), run(8192, k, "packed")
            assert a["sha256"] == b["sha256"] and a["sum"] == b["sum"]
            for backend, start in (
                ("dense", 12288),
                ("packed", 19456 if k == 8 else 15360),
            ):
                n = start
                previous = None
                while n <= 32768:
                    row = run(n, k, backend)
                    if row["status"] == "over_budget":
                        if previous is None:
                            n -= 1024
                            # Find a completed lower point; no monotonic upper scan.
                            while n >= 8192:
                                row = run(n, k, backend)
                                if row["status"] == "completed":
                                    break
                                n -= 1024
                        break
                    previous = row
                    n += 1024


if __name__ == "__main__":
    main()
