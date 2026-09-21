"""All cold packing sites retain exact records and ordered codec inputs."""

import inspect
import random

import pytest

import tightarray.compressed as live
from benchmarks.compressed_all_payloads import cases, inject, pair


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
@pytest.mark.parametrize("palette", [False, True])
def test_exact_records_and_calls(codec, palette):
    if codec != "none":
        pytest.importorskip("blosc2")
    rng = random.Random(93)
    inputs = [raw for _, raw in cases()]
    inputs += [
        bytes(rng.randrange(128, 136) for _ in range(size)) for size in range(1, 81)
    ]
    with pair(inspect.getsource(live)) as (modules, _):
        results = {}
        for key, module in modules.items():
            array = module.CompressedArray(b"", codec=codec, palette=palette)
            calls = []
            original = array._compress

            def record(raw, *, shuffle, calls=calls, original=original):
                calls.append((raw, shuffle))
                return original(raw, shuffle=shuffle)

            array._compress = record
            results[key] = ([array._encode(raw) for raw in inputs], calls)
        assert results["baseline"] == results["reuse"]


def test_idempotence():
    once = inject(inspect.getsource(live))
    assert inject(once) == once
