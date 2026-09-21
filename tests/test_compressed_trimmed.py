"""Integrated structural spans must preserve ordinary array write semantics."""

import random

import pytest

from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
@pytest.mark.parametrize("budget", [0, 512, 65536])
@pytest.mark.parametrize("palette", [False, True])
def test_trimmed_boundary_reads_and_mutations(codec, budget, palette):
    if codec != "none":
        pytest.importorskip("blosc2")
    rng = random.Random(804)
    raw = bytes(512) + bytes(rng.randrange(1, 32) for _ in range(1024)) + bytes(2560)
    expected = bytearray(raw + raw[:1701])
    array = CompressedArray(
        expected, chunk_size=4096, cache_bytes=budget, codec=codec, palette=palette
    )
    assert array.storage_info().trimmed_chunks >= 1
    assert array.tobytes() == expected
    assert array[::-31] == expected[::-31]
    for first, last in ((0, 0), (500, 550), (1500, 1600), (4000, 4200)):
        assert array.read(first, last) == expected[first:last]
    for index in (0, 511, 512, 1535, 1536, 4095, -1):
        array[index] = 255
        expected[index] = 255
    array.write(1520, bytes(range(64)))
    expected[1520:1584] = bytes(range(64))
    array.clear_cache()
    assert array.tobytes() == expected
    assert array.storage_info().cache_bytes <= budget


def test_trim_failure_preserves_cached_span(monkeypatch):
    rng = random.Random(51)
    raw = bytes(1024) + bytes(rng.randrange(32) for _ in range(256)) + bytes(2816)
    array = CompressedArray(raw, cache_bytes=256)
    assert array.storage_info().trimmed_chunks == 1
    assert array[0] == 0
    before = array.storage_info().cache_bytes

    def fail(_raw):
        raise RuntimeError("replacement failed")

    monkeypatch.setattr(array, "_encode", fail)
    array[0] = 0  # No change must retain the structural entry.
    with pytest.raises(RuntimeError, match="replacement failed"):
        array[0] = 31
    assert array.tobytes() == raw
    assert array.storage_info().cache_bytes == before


def test_large_chunks_skip_uint16_trim_descriptor():
    raw = bytes(range(32)) * 1024 + bytes(32768)
    array = CompressedArray(raw, chunk_size=65536)
    assert array.storage_info().trimmed_chunks == 0
    assert array.tobytes() == raw
