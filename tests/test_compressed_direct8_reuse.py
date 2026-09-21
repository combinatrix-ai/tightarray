"""The isolated candidate preserves sealed output and codec call ordering."""

import inspect
import random

import pytest

import tightarray.compressed as live
from benchmarks.compressed_direct8_reuse import cases, inject, pair


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
@pytest.mark.parametrize("palette", [False, True])
def test_exact_records_and_compression_calls(codec, palette):
    if codec != "none":
        pytest.importorskip("blosc2")
    rng = random.Random(921)
    inputs = [raw for _, raw in cases()]
    inputs += [bytes(rng.randrange(256) for _ in range(size)) for size in range(1, 81)]
    with pair(inspect.getsource(live)) as (modules, _):
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


def test_direct_payload_identity_padding_and_controls():
    with pair(inspect.getsource(live)) as (modules, _):
        fn = modules["reuse"]._direct_payload
        for length in range(1, 81):
            raw = bytes((i * 7) % 256 for i in range(length))
            result = fn(raw, 8)
            assert result == live._raw(live.Array(raw, bits=8))
            if length % 8 == 0:
                assert result is raw
        for bits in range(1, 8):
            raw = bytes(i % (1 << bits) for i in range(79))
            assert fn(raw, bits) == live._raw(live.Array(raw, bits=bits))


def test_injection_idempotent():
    once = inject(inspect.getsource(live))
    assert inject(once) == once
