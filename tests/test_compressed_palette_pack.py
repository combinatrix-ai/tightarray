"""Fused mapping preserves cold records and every codec candidate."""

import inspect
import random

import pytest

import tightarray.compressed as live
from benchmarks.compressed_palette_pack import cases, inject, pair


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
@pytest.mark.parametrize("palette", [False, True])
def test_fused_palette_exact(codec, palette):
    if codec != "none":
        pytest.importorskip("blosc2")
    source = inspect.getsource(live)
    rng = random.Random(1283)
    inputs = [raw for _, raw in cases()]
    for count in (2, 8, 32, 128):
        for length in (1, 7, 8, 9, 31, 64, 65, 511, 512, 513, 1023, 1024, 1025):
            inputs.append(bytes(rng.randrange(256 - count, 256) for _ in range(length)))
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
            chunks = [arr._encode(raw) for raw in inputs]
            results[key] = (chunks, calls)
        assert results["baseline"] == results["reuse"]


def test_injection_idempotent():
    source = inject(inspect.getsource(live))
    assert inject(source) == source
