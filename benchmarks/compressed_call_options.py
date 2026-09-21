"""Exact-output comparison of Blosc wrapper and immutable filter arguments."""

import argparse
import hashlib
import inspect
import json
import random
import statistics
import time
from pathlib import Path

import blosc2

from benchmarks.compressed_trimmed_policy import guards


def compress(raw, codec, shuffle, policy):
    function = (
        blosc2.blosc2_ext.compress2
        if policy.startswith("extension")
        else blosc2.compress2
    )
    filter_value = blosc2.Filter.BITSHUFFLE if shuffle else blosc2.Filter.NOFILTER
    if policy.endswith("tuple"):
        return function(
            raw,
            codec=codec,
            typesize=1,
            clevel=5,
            nthreads=1,
            filters=(filter_value,),
            filters_meta=(0,),
        )
    return function(
        raw, codec=codec, typesize=1, clevel=5, nthreads=1, filters=[filter_value]
    )


def datasets():
    rng = random.Random(9821)
    for size in (64, 512, 4096):
        yield f"random8-{size}", bytes(rng.randrange(256) for _ in range(size))
        yield f"two-high-{size}", bytes(rng.choice((200, 255)) for _ in range(size))
        yield f"runs-{size}", bytes((i // 32) % 32 for i in range(size))


def source_guards():
    values = guards()
    for path in (
        Path(__file__),
        Path(blosc2.__file__),
        Path(inspect.getfile(blosc2.compress2)),
        Path(blosc2.blosc2_ext.__file__),
    ):
        values[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return values


def run(repeats=11, calls=64):
    frozen = source_guards()
    rng = random.Random(3194)
    policies = ("public-list", "public-tuple", "extension-list", "extension-tuple")
    records = []
    for name, raw in datasets():
        for codec in (blosc2.Codec.LZ4, blosc2.Codec.ZSTD):
            for shuffle in (False, True):
                expected = compress(raw, codec, shuffle, "public-list")
                assert blosc2.decompress2(expected, nthreads=1) == raw
                for policy in policies:
                    assert compress(raw, codec, shuffle, policy) == expected
                samples = {policy: [] for policy in policies}
                for _ in range(repeats):
                    order = list(policies)
                    rng.shuffle(order)
                    for policy in order:
                        start = time.perf_counter_ns()
                        for _ in range(calls):
                            result = compress(raw, codec, shuffle, policy)
                        elapsed = time.perf_counter_ns() - start
                        assert result == expected
                        samples[policy].append(elapsed / calls)
                records.append(
                    {
                        "case": name,
                        "codec": codec.name,
                        "shuffle": shuffle,
                        "input_bytes": len(raw),
                        "output_bytes": len(expected),
                        "samples_ns": samples,
                        "median_ns": {
                            key: statistics.median(value)
                            for key, value in samples.items()
                        },
                    }
                )
    assert frozen == source_guards(), "Measured sources changed"
    return {
        "blosc2": blosc2.__version__,
        "repeats": repeats,
        "calls_per_sample": calls,
        "source_sha256": frozen,
        "records": records,
        "scope": "One common Python dispatcher wraps every policy; this isolates wrapper/filter-argument choices, not complete CompressedArray throughput. No context retention. Exact compressed bytes and decoded values checked; timing includes result allocation/free.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=11)
    parser.add_argument("--calls", type=int, default=64)
    args = parser.parse_args()
    if args.repeats < 1 or args.calls < 1:
        parser.error("positive repeats and calls required")
    Path(args.output).write_text(
        json.dumps(run(args.repeats, args.calls), indent=2) + "\n"
    )
