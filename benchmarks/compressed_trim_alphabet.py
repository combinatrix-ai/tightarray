"""Compare isolated old/new native trim planners and complete encoders."""

import argparse
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def cases():
    rng = random.Random(901)
    for size in (512, 4096, 16384):
        for bits in (3, 5, 8):
            for present in (False, True):
                middle = bytes(
                    rng.randrange(0 if present else 1, 1 << bits)
                    for _ in range(size // 2)
                )
                yield (
                    f"span-{size}-{bits}-{present}",
                    bytes(size // 4) + middle + bytes(size // 4),
                )
        yield f"random-{size}", bytes(rng.randrange(32) for _ in range(size))
        yield (
            f"opposed-{size}",
            bytes(size // 4)
            + bytes(rng.randrange(1, 31) for _ in range(size // 2))
            + bytes([31]) * (size // 4),
        )


def worker(path, repeats, calls):
    import tightarray._core as core

    from tightarray.compressed import CompressedArray

    package = Path(core.__file__).parent
    files = [*package.glob("*.py"), Path(core.__file__)]
    frozen = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    rows = []
    for name, raw in cases():
        colors = bytes(sorted(set(raw)))
        for palette in (False, True):
            for kind in ("planner", "none", "lz4", "zstd"):
                if kind == "planner":
                    fn = lambda raw=raw, colors=colors, palette=palette: (
                        core._trim_plan(raw, colors, palette, len(raw) + 2)
                    )
                else:
                    arr = CompressedArray(b"", codec=kind, palette=palette)
                    fn = lambda arr=arr, raw=raw: arr._encode(raw)
                expected = fn()
                samples = []
                for _ in range(repeats):
                    start = time.perf_counter_ns()
                    for _ in range(calls):
                        result = fn()
                    samples.append((time.perf_counter_ns() - start) / calls)
                    assert result == expected
                rows.append(
                    {
                        "case": name,
                        "palette": palette,
                        "kind": kind,
                        "sha256": hashlib.sha256(repr(expected).encode()).hexdigest(),
                        "median_ns": statistics.median(samples),
                        "ns": samples,
                    }
                )
    assert frozen == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    Path(path).write_text(
        json.dumps({"sources": frozen, "rows": rows}, indent=2) + "\n"
    )


def run(old, new, pairs, repeats, calls):
    rng = random.Random(902)
    groups = []
    script = Path(__file__).resolve()
    script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as directory:
        for pair in range(pairs):
            order = [("old", old), ("new", new)]
            rng.shuffle(order)
            group = {}
            for label, package in order:
                path = Path(directory) / f"{pair}-{label}.json"
                env = os.environ.copy()
                env["PYTHONPATH"] = str(Path(package).resolve())
                subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--worker",
                        str(path),
                        "--repeats",
                        str(repeats),
                        "--calls",
                        str(calls),
                    ],
                    cwd=directory,
                    env=env,
                    check=True,
                )
                group[label] = json.loads(path.read_text())
                assert all(
                    Path(p).is_relative_to(Path(package).resolve())
                    for p in group[label]["sources"]
                )
            assert [
                (r["case"], r["palette"], r["kind"], r["sha256"])
                for r in group["old"]["rows"]
            ] == [
                (r["case"], r["palette"], r["kind"], r["sha256"])
                for r in group["new"]["rows"]
            ]
            groups.append(group)
    assert hashlib.sha256(script.read_bytes()).hexdigest() == script_hash
    return {
        "pairs": groups,
        "repeats": repeats,
        "calls": calls,
        "script_sha256": script_hash,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--old")
    parser.add_argument("--new")
    parser.add_argument("--output")
    parser.add_argument("--worker")
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=11)
    parser.add_argument("--calls", type=int, default=100)
    args = parser.parse_args()
    if min(args.pairs, args.repeats, args.calls) < 1:
        parser.error("pairs, repeats and calls must be positive")
    if args.worker:
        worker(args.worker, args.repeats, args.calls)
    else:
        Path(args.output).write_text(
            json.dumps(
                run(args.old, args.new, args.pairs, args.repeats, args.calls), indent=2
            )
            + "\n"
        )
