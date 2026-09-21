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


@pytest.mark.parametrize("palette", [False, True])
def test_inside_span_write_retains_entry_and_failed_flush(monkeypatch, palette):
    rng = random.Random(811)
    colors = [200, 201, 202, 203]
    interior = bytes(rng.choice(colors) for _ in range(512))
    expected = bytearray(bytes(1024) + interior + bytes(2560))
    array = CompressedArray(expected, cache_bytes=512, palette=palette)
    assert array.storage_info().trimmed_chunks == 1
    assert array[1024] == expected[1024]
    before = array.storage_info().cache_bytes
    entry = array._cache[0]

    def fail(_raw):
        raise RuntimeError("flush failed")

    original_encode = array._encode
    monkeypatch.setattr(array, "_encode", fail)
    for index in (1024, 1100, 1535):
        value = colors[(colors.index(expected[index]) + 1) % 4]
        array[index] = value
        expected[index] = value
        assert array._cache[0] is entry
        assert array.storage_info().cache_bytes == before
    with pytest.raises(RuntimeError, match="flush failed"):
        array.clear_cache()
    assert array._cache[0] is entry
    assert entry.dirty
    assert array.tobytes() == expected
    monkeypatch.setattr(array, "_encode", original_encode)
    array.clear_cache()
    assert array.tobytes() == expected


@pytest.mark.parametrize("budget", [0, 32])
def test_uncached_span_inside_write_reaches_cold_storage(budget):
    rng = random.Random(812)
    raw = bytes(512) + bytes(rng.randrange(32) for _ in range(1024)) + bytes(2560)
    array = CompressedArray(raw, cache_bytes=budget)
    assert array.storage_info().trimmed_chunks == 1
    expected = bytearray(raw)
    expected[700] = (expected[700] + 1) % 32
    array[700] = expected[700]
    assert array.storage_info().cache_bytes == 0
    array.clear_cache()
    assert array.tobytes() == expected
