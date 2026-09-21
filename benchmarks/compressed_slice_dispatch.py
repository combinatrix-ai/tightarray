"""Slice overhead control for index-first compressed-array scalar dispatch."""

import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path

from benchmarks.compressed_period_policy import pinned, provenance
from tightarray.compressed import CompressedArray


def run():
    before = provenance()
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rng = random.Random(898)
    raw = bytes(rng.randrange(8) for _ in range(8192))
    records = []
    with pinned("65c7a89") as (base, _):
        arrays = {"baseline": base(raw), "current": CompressedArray(raw)}
        for name, key in (
            ("empty", slice(512, 512)),
            ("one", slice(512, 513)),
            ("64", slice(512, 576)),
            ("4096", slice(512, 4608)),
            ("strided", slice(512, 768, 7)),
        ):
            expected = raw[key]
            for array in arrays.values():
                assert array[key] == expected
            samples = {label: [] for label in arrays}
            for _ in range(9):
                order = list(arrays)
                rng.shuffle(order)
                for label in order:
                    started = time.perf_counter_ns()
                    for _ in range(2000):
                        result = arrays[label][key]
                    elapsed = time.perf_counter_ns() - started
                    assert result == expected
                    samples[label].append(elapsed / 1e6)
            records.append(
                {
                    "slice": name,
                    "samples_ms": samples,
                    "median_ms": {k: statistics.median(v) for k, v in samples.items()},
                }
            )
    assert before == provenance()
    assert script_hash == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "baseline": "65c7a89",
        "source_sha256": before,
        "script_sha256": script_hash,
        "seed": 898,
        "operations": 2000,
        "repeats": 9,
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(), indent=2) + "\n")
