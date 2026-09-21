"""Robust public-write confirmation after initial native memcpy study.

Historical artifact untouched.31 independently reconstructed warm trials per
configuration and5 randomized old/new process pairs isolate short-phase noise.
"""

import argparse
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from benchmarks.compressed_memcpy import hashes


def worker(output):
    import tightarray._core as core

    import tightarray
    import tightarray.compressed as live
    from benchmarks.compressed_hot_bulk import cases, make_trace, trial

    config = [
        (name, width, codec)
        for name in ("direct-8bit", "direct-5bit")
        for width in (1, 16, 64, 256)
        for codec in ("none", "zstd")
    ]
    random.Random(740).shuffle(config)
    fixture = cases()
    rows = []
    for name, width, codec in config:
        data, labels = fixture[name]
        writes, expected, changed = make_trace(data, labels, width, count=17)
        samples = []
        first = None
        for _ in range(31):
            result = trial(
                live.CompressedArray, f"palette-{codec}", data, 65536, writes, expected
            )
            samples.append(result["writes_flush_ms"])
            if first is None:
                first = {k: v for k, v in result.items() if k != "writes_flush_ms"}
            else:
                assert result["cold_sha256"] == first["cold_sha256"]
                for phase in ("before", "after", "reloaded"):
                    for field in ("stored_bytes", "cache_bytes"):
                        assert result[phase][field] == first[phase][field]
        rows.append(
            {
                "case": name,
                "width": width,
                "codec": codec,
                "write_count": 17,
                "changes": changed,
                "trials_ms": samples,
                "median_ms": statistics.median(samples),
                "storage": first,
            }
        )
    result = {
        "rows": rows,
        "package": str(Path(tightarray.__file__).parent),
        "binary_sha256": hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest(),
    }
    Path(output).write_text(json.dumps(result, indent=2) + "\n")


def run(baseline, candidate, repeats=5):
    root = Path(__file__).resolve().parents[1]
    paths = [
        Path(__file__),
        *(root / "benchmarks").glob("compressed_memcpy.py"),
        root / "benchmarks/compressed_hot_bulk.py",
        root / "benchmarks/compressed_span_bulk.py",
        root / "benchmarks/compressed_trimmed_policy.py",
        root / "benchmarks/compressed_storage.py",
        root / "tightarray/_core.c",
        *(root / "tightarray").glob("_compressed*.h"),
    ]

    def guards():
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths
        }

    before = guards()
    packages = {
        "base": str(Path(baseline).resolve()),
        "live": str(Path(candidate).resolve()),
    }
    manifests = {k: hashes(v) for k, v in packages.items()}
    assert {k: v for k, v in manifests["base"].items() if k.endswith(".py")} == {
        k: v for k, v in manifests["live"].items() if k.endswith(".py")
    }
    samples = {k: [] for k in packages}
    rng = random.Random(741)
    with tempfile.TemporaryDirectory(prefix="ta-memcpy-confirm-") as tmp:
        for i in range(repeats):
            order = list(packages)
            rng.shuffle(order)
            for label in order:
                output = Path(tmp) / f"{i}-{label}.json"
                env = dict(os.environ)
                env["PYTHONPATH"] = packages[label] + os.pathsep + str(root)
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        "--output",
                        str(output),
                    ],
                    env=env,
                    cwd=tmp,
                    check=True,
                )
                samples[label].append(json.loads(output.read_text()))
                print(i, label, "complete", flush=True)
    assert before == guards()
    assert manifests == {k: hashes(v) for k, v in packages.items()}
    return {
        "python_commit": "6ea92e7",
        "package_sha256": manifests,
        "source_sha256": before,
        "process_pairs": repeats,
        "trials_per_config_per_worker": 31,
        "samples": samples,
        "scope": "Follow-up confirmation after initial200configurationstudy; initial artifact unchanged. Direct8target/direct5control,4widths,none/ZSTD,cache65536.31fresh-object warm trials per config per worker; summarize medians withinworker then across5independent randomizedprocesspairs.17realchangingwrites+flush; constructors/imports excluded, allcontent/reload/cache assertions pass. Separate old/new.so with identical pinnedPython; no new kernel edits.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--baseline")
    parser.add_argument("--candidate")
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.worker:
        worker(args.output)
    else:
        if not args.baseline or not args.candidate or args.repeats < 1:
            parser.error("baseline,candidate and positive repeats required")
        Path(args.output).write_text(
            json.dumps(run(args.baseline, args.candidate, args.repeats), indent=2)
            + "\n"
        )
