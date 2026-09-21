"""Paired repeated/no-op writes versus Python policy before early return.

This measures a specific workload, not general update performance. Baseline
Python is pinned to 1c1fb1c, sharing the installed native extension.
"""

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
    records = []
    rng = random.Random(493)
    raw = bytes(range(200, 231)) * 132
    with pinned("1c1fb1c") as (baseline, source):
        for codec in ("none", "zstd"):
            for budget in (0, 64, 65536):
                for changed in (False, True):
                    samples = {"baseline": [], "current": []}
                    for _ in range(7):
                        order = list(samples)
                        rng.shuffle(order)
                        for name in order:
                            cls = baseline if name == "baseline" else CompressedArray
                            array = cls(
                                raw,
                                chunk_size=len(raw),
                                cache_bytes=budget,
                                codec=codec,
                            )
                            assert array[0] == raw[0]
                            expected = bytearray(raw)
                            started = time.perf_counter_ns()
                            for index in range(64):
                                value = raw[index] ^ int(changed)
                                array[index] = value
                            array.flush()
                            elapsed = time.perf_counter_ns() - started
                            for index in range(64):
                                expected[index] = raw[index] ^ int(changed)
                            assert array.tobytes() == expected
                            assert array.storage_info().cache_bytes <= budget
                            samples[name].append(elapsed / 1e6)
                    records.append(
                        {
                            "codec": codec,
                            "cache_bytes": budget,
                            "changed": changed,
                            "samples_ms": samples,
                            "median_ms": {
                                k: statistics.median(v) for k, v in samples.items()
                            },
                        }
                    )
    assert before == provenance(), "measured sources changed"
    assert script_hash == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "baseline_commit": "1c1fb1c",
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "script_sha256": script_hash,
        "seed": 493,
        "writes_per_trial": 64,
        "repeats": 7,
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(), indent=2) + "\n")
