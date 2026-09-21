"""Paired native Hot comparison with the Python cache entry at commit 1fb408a.

Run as python -m benchmarks.compressed_hot_paired --output /tmp/result.json.
Requires a Git checkout containing that baseline commit. The baseline uses the
current native Array helpers; only Python cache-entry implementation is restored.
"""

import argparse
import json
import random
import statistics
import subprocess
import sys
import types
from pathlib import Path

import tightarray.compressed as live
from benchmarks.compressed_storage import dataset, source_hashes, traces, trial


def run(output: Path) -> None:
    base = types.ModuleType("tightarray._hot_baseline")
    base.__package__ = "tightarray"
    sys.modules[base.__name__] = base
    source = subprocess.check_output(
        ["git", "show", "1fb408a:tightarray/compressed.py"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
    )
    # Execute only the explicitly pinned repository baseline for the comparison.
    exec(compile(source, "baseline_compressed.py", "exec"), base.__dict__)  # noqa: S102
    classes = {"python": base.CompressedArray, "native": live.CompressedArray}
    rng = random.Random(421)
    rows = []
    try:
        for case in [
            "random8",
            "random32",
            "local-two",
            "uniform-chunks",
            "runs32",
            "rare-spikes",
        ]:
            data = dataset(case, 1 << 20, 4096)
            ops = traces(data, 4096)
            samples = {key: [] for key in classes}
            for repeat in range(9):
                order = list(classes)
                rng.shuffle(order)
                for key in order:
                    live.CompressedArray = classes[key]
                    samples[key].append(trial(data, "palette-none", 4096, 65536, ops))
            rows.append({"case": case, "samples": samples})
    finally:
        live.CompressedArray = classes["native"]
    result = {
        "baseline_commit": "1fb408a",
        "source_sha256": source_hashes(),
        "repeats": 9,
        "seed": 421,
        "rows": rows,
    }
    output.write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(
            row["case"],
            {
                key: {
                    metric: round(statistics.median(r[metric] for r in rows), 4)
                    for metric in [
                        "local_scalar_ms",
                        "global_scalar_ms",
                        "read64_ms",
                        "updates_flush_ms",
                    ]
                }
                for key, rows in row["samples"].items()
            },
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
