"""Refresh the broad storage comparison with complete native source guards."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from benchmarks.compressed_storage import run
from benchmarks.compressed_values_bytes import guards


def refresh(size=1 << 20, repeats=5):
    before = guards()
    own = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result = run(size=size, repeats=repeats)
    assert before == guards()
    assert own == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["metadata"]["complete_source_sha256"] = before
    result["metadata"]["refresh_script_sha256"] = own
    result["metadata"]["scope"] = (
        "Current production only; experimental context pools excluded. Same-run comparisons, not historical before/after ratios. Native binary and all headers guarded."
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", type=int, default=1 << 20)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if min(args.size, args.repeats) < 1:
        parser.error("positive size and repeats required")
    raw = (json.dumps(refresh(args.size, args.repeats), indent=2) + "\n").encode()
    Path(args.output).write_bytes(
        gzip.compress(raw, mtime=0) if args.output.endswith(".gz") else raw
    )
