"""Native packing preserves encoded records and candidate codec inputs."""

import inspect
import random

import pytest

import tightarray.compressed as live
from benchmarks.compressed_native_payload import cases, pair


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
@pytest.mark.parametrize("palette", [False, True])
def test_native_candidate_exact(codec, palette):
    if codec != "none":
        pytest.importorskip("blosc2")
    source = inspect.getsource(live).replace(
        "return _native._pack_bytes(raw, bits)", "return _raw(Array(raw, bits=bits))"
    )
    rng = random.Random(516)
    inputs = [raw for _, raw in cases()]
    for bits in range(1, 9):
        for size in (1, 7, 8, 9, 15, 16, 17, 63, 64, 65, 127):
            inputs.append(bytes(rng.randrange(1 << bits) for _ in range(size)))
    with pair(source) as (modules, _):
        results = {}
        for key, module in modules.items():
            arr = module.CompressedArray(b"", codec=codec, palette=palette)
            calls = []
            original = arr._compress

            def record(raw, *, shuffle, calls=calls, original=original):
                calls.append((raw, shuffle))
                return original(raw, shuffle=shuffle)

            arr._compress = record
            results[key] = ([arr._encode(raw) for raw in inputs], calls)
        assert results["baseline"] == results["reuse"]
