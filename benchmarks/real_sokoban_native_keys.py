"""Actual Sokoban search with fused native packed-key construction."""

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np

import benchmarks.real_sokoban_search as upstream
from benchmarks.compressed_values_bytes import guards
from tightarray import _core


def native_key(board):
    return _core._pack_bytes(board.astype(np.uint8).tobytes(), 3)


def worker(backend, limit):
    original = upstream.encode

    def encode(board, method, fixed):
        return (
            native_key(board) if method == "native" else original(board, method, fixed)
        )

    upstream.encode = encode
    try:
        return upstream.run_case(upstream.SOURCE, 37, backend, limit)
    finally:
        upstream.encode = original


def run():
    frozen = guards()
    own = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    samples = []
    for limit in (5000, 50000):
        for repeat in range(5):
            methods = ["marshal", "uint8", "tightarray", "native", "sparse"]
            random.Random(8410 + repeat).shuffle(methods)
            for method in methods:
                result = subprocess.check_output(
                    [
                        sys.executable,
                        "-m",
                        "benchmarks.real_sokoban_native_keys",
                        "--worker",
                        method,
                        "--limit",
                        str(limit),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    text=True,
                )
                samples.append(json.loads(result))
            print(limit, repeat, "complete", flush=True)
    assert frozen == guards()
    assert own == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows = []
    for limit in (5000, 50000):
        chosen = [x for x in samples if x["limit"] == limit]
        assert all(x["identity"] == chosen[0]["identity"] for x in chosen)
        for method in ("marshal", "uint8", "tightarray", "native", "sparse"):
            values = [x for x in chosen if x["backend"] == method]
            rows.append(
                {
                    "limit": limit,
                    "backend": method,
                    "median_s": statistics.median(x["elapsed_s"] for x in values),
                    "retained_key_set_bytes": values[0]["retained_key_set_bytes"],
                    "visited": values[0]["identity"]["visited"],
                }
            )
    return {
        "source_sha256": frozen,
        "script_sha256": own,
        "upstream_commit": upstream.COMMIT,
        "upstream_sha256": upstream.SOURCE_SHA256,
        "samples": samples,
        "rows": rows,
        "scope": "Real upstream search, seed37,5 fresh workers per backend/cap; startup excluded. Key encoder only changed. Retained set sizes are not RSS. Native helper is private experimental API.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--output", default="/tmp/ta-sokoban-native-results.json")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, args.limit)))
    else:
        Path(args.output).write_text(json.dumps(run(), indent=2) + "\n")
