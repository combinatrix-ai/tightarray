"""Paired exact-int dispatch experiment, including index-protocol controls."""

import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path

import numpy as np

from benchmarks.compressed_period_policy import pinned, provenance
from tightarray.compressed import CompressedArray


class Index:
    def __init__(self, value):
        self.value = value

    def __index__(self):
        return self.value


class IntSubclass(int):
    def __index__(self):
        raise AssertionError("operator.index must normalize int subclasses")


def run():
    before = provenance()
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rng = random.Random(897)
    raw = bytes(rng.randrange(8) for _ in range(32768))
    records = []
    with pinned("65c7a89") as (base, source):
        for kind, data in (
            ("packed", raw),
            ("uniform", bytes(len(raw))),
            ("periodic", (bytes(range(31)) * 1058)[: len(raw)]),
        ):
            for key_kind, convert in (
                ("int", int),
                ("numpy", np.int64),
                ("index", Index),
                ("subclass", IntSubclass),
            ):
                indexes = [rng.randrange(len(data)) for _ in range(256)]
                indexes[::4] = [value - len(data) for value in indexes[::4]]
                keys = [convert(value) for value in indexes]
                expected = 64 * sum(data[value] for value in indexes)
                arrays = {
                    "baseline": base(data, cache_bytes=65536),
                    "current": CompressedArray(data, cache_bytes=65536),
                }
                for array in arrays.values():
                    for key in keys:
                        array[key]
                    assert array[True] == data[1]
                    assert array[::-19] == data[::-19]
                    for key in (len(data), -len(data) - 1):
                        try:
                            array[key]
                        except IndexError:
                            pass
                        else:
                            raise AssertionError("out-of-bounds access accepted")
                samples = {name: [] for name in arrays}
                for _ in range(9):
                    order = list(arrays)
                    rng.shuffle(order)
                    for name in order:
                        array = arrays[name]
                        total = 0
                        started = time.perf_counter_ns()
                        for _ in range(64):
                            for key in keys:
                                total += array[key]
                        elapsed = time.perf_counter_ns() - started
                        assert total == expected
                        samples[name].append(elapsed / 1e6)
                records.append(
                    {
                        "data": kind,
                        "key": key_kind,
                        "samples_ms": samples,
                        "median_ms": {
                            k: statistics.median(v) for k, v in samples.items()
                        },
                    }
                )
    assert before == provenance()
    assert own_hash == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "baseline": "65c7a89",
        "baseline_python_sha256": hashlib.sha256(source).hexdigest(),
        "source_sha256": before,
        "script_sha256": own_hash,
        "seed": 897,
        "operations": 16384,
        "repeats": 9,
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(), indent=2) + "\n")
