"""Refresh actual MiniGrid replay and bounded upstream Sokoban search."""

import argparse
import gzip
import hashlib
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path


def source_guards(source):
    import gymnasium
    import minigrid
    import tightarray._core as core

    root = Path(__file__).resolve().parents[1]
    paths = [
        Path(__file__),
        Path(source),
        Path(core.__file__),
        root / "benchmarks/real_minigrid_replay.py",
        root / "benchmarks/real_sokoban_search.py",
    ]
    paths += list((root / "tightarray").rglob("*.py"))
    paths += list((root / "tightarray").glob("*.h"))
    paths += list((root / "tightarray").glob("*.c"))
    for module in (gymnasium, minigrid):
        paths += list(Path(module.__file__).parent.rglob("*.py"))
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def worker(kind, source, backend, limit):
    frozen = source_guards(source)
    if kind == "minigrid":
        from benchmarks.real_minigrid_replay import run

        result = run()
    else:
        from benchmarks.real_sokoban_search import run_case

        result = run_case(source, 37, backend, limit)
    assert frozen == source_guards(source), "Measured source changed"
    return {"kind": kind, "source_sha256": frozen, "result": result}


def run(source, repeats=3):
    root = Path(__file__).resolve().parents[1]
    frozen = source_guards(source)
    env = dict(os.environ, PYTHONPATH=str(root))
    rng = random.Random(8401)
    runs = []
    with tempfile.TemporaryDirectory(prefix="ta-application-refresh-") as tmp:

        def execute(kind, backend="marshal", limit=5000):
            output = Path(tmp) / "worker.json"
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    kind,
                    "--source",
                    source,
                    "--backend",
                    backend,
                    "--limit",
                    str(limit),
                    "--output",
                    str(output),
                ],
                cwd=tmp,
                env=env,
                check=True,
            )
            record = json.loads(output.read_text())
            assert frozen == record["source_sha256"]
            return record["result"]

        minigrid = execute("minigrid")
        print("MiniGrid replay complete", flush=True)
        for limit in (5000, 50000):
            names = ["marshal", "uint8", "tightarray", "sparse"]
            rng.shuffle(names)
            reference = None
            for repeat in range(repeats):
                order = names[repeat % 4 :] + names[: repeat % 4]
                for backend in order:
                    result = execute("sokoban", backend, limit)
                    if reference is None:
                        reference = result["identity"]
                    assert reference == result["identity"]
                    result["repeat"] = repeat
                    runs.append(result)
                    print(
                        "Sokoban",
                        limit,
                        repeat,
                        backend,
                        result["elapsed_s"],
                        flush=True,
                    )
    assert frozen == source_guards(source)
    summary = []
    for limit in (5000, 50000):
        for backend in ("marshal", "uint8", "tightarray", "sparse"):
            rows = [x for x in runs if x["limit"] == limit and x["backend"] == backend]
            for key in ("key_payload_bytes", "retained_key_set_bytes"):
                assert len({x[key] for x in rows}) == 1
            summary.append(
                {
                    "limit": limit,
                    "backend": backend,
                    "median_s": statistics.median(x["elapsed_s"] for x in rows),
                    "key_payload_bytes": rows[0]["key_payload_bytes"],
                    "retained_key_set_bytes": rows[0]["retained_key_set_bytes"],
                    "identity": rows[0]["identity"],
                }
            )
    return {
        "metadata": {
            "head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            "source_sha256": frozen,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "sokoban_repeats": repeats,
            "source": source,
            "seed": 37,
            "order_seed": 8401,
            "scope": "Fresh process per Sokoban sample and MiniGrid matrix; import/startup excluded. "
            "Actual upstream capped search and actual observation replay, not RL training. "
            "Memory is payload or retained keyset, not RSS. New packed bulk mutation SIMD "
            "is not claimed to be exercised by these encoding/read workloads.",
        },
        "minigrid": minigrid,
        "sokoban_samples": runs,
        "sokoban_summary": summary,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source", default="/tmp/tightarray-sokoban-source/room_utils.py"
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--worker", choices=("minigrid", "sokoban"))
    parser.add_argument("--backend", default="marshal")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    result = (
        worker(args.worker, args.source, args.backend, args.limit)
        if args.worker
        else run(args.source, args.repeats)
    )
    raw = (json.dumps(result, indent=2) + "\n").encode()
    args.output.write_bytes(
        gzip.compress(raw, mtime=0) if args.output.suffix == ".gz" else raw
    )
