"""Periodic cold records preserve partial tails and isolate individual writes."""

import pytest

from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
@pytest.mark.parametrize("budget", [0, 64, 65536])
def test_periodic_records_mutation_and_partial_tails(codec, budget):
    if codec != "none":
        pytest.importorskip("blosc2")
    pattern = bytes(range(200, 231))
    expected = bytearray((pattern * 101)[:3107])
    array = CompressedArray(expected, chunk_size=509, cache_bytes=budget, codec=codec)
    assert array.storage_info().periodic_chunks >= 6
    assert array.tobytes() == expected
    for index, value in [(0, 0), (31, 255), (509, 99), (3106, 22)]:
        array[index] = value
        expected[index] = value
        assert array[index] == value
    array.write(497, bytes(range(61)))
    expected[497:558] = bytes(range(61))
    assert array.tobytes() == expected
    array.clear_cache()
    assert array.tobytes() == expected
    assert array[::-17] == expected[::-17]
    assert array.storage_info().cache_bytes <= budget


def test_late_mismatch_cannot_be_saved_as_periodic():
    raw = b"ab" * 2048 + b"c"
    array = CompressedArray(raw, chunk_size=len(raw))
    assert array.storage_info().periodic_chunks == 0
    assert array.tobytes() == raw


def test_failed_period_materialization_keeps_original_cached_pattern(monkeypatch):
    raw = bytes(range(31)) * 32
    array = CompressedArray(raw, chunk_size=len(raw), cache_bytes=64)
    assert array[0] == 0  # Admit the small cyclic pattern.

    def fail(_raw):
        raise RuntimeError("cannot write replacement")

    monkeypatch.setattr(array, "_encode", fail)
    with pytest.raises(RuntimeError, match="cannot write replacement"):
        array[0] = 2  # Fits existing width, but must not mutate every repetition.
    assert array.tobytes() == raw
    assert array[31] == 0
    assert array.storage_info().cache_bytes <= 64


@pytest.mark.parametrize("budget", [0, 64, 65536])
@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
def test_same_value_periodic_write_does_not_materialize(monkeypatch, budget, codec):
    if codec != "none":
        pytest.importorskip("blosc2")
    raw = bytes(range(200, 231)) * 32
    array = CompressedArray(raw, chunk_size=len(raw), cache_bytes=budget, codec=codec)
    assert array.storage_info().periodic_chunks == 1
    assert array[0] == 200
    before = array.storage_info()

    def fail(_raw):
        raise AssertionError("unchanged periodic data must not materialize")

    monkeypatch.setattr(array, "_make_hot", fail)
    monkeypatch.setattr(array, "_encode", fail)
    for index in (0, 31, -1):
        array[index] = raw[index]
    array.flush()
    assert array.tobytes() == raw
    after = array.storage_info()
    assert after.cache_bytes == before.cache_bytes
    assert after.stored_bytes == before.stored_bytes
    with pytest.raises(ValueError):
        array[0] = 256
    with pytest.raises(IndexError):
        array[len(raw)] = 200


@pytest.mark.parametrize(
    "pattern,repeats,payload,palette_size",
    [
        (bytes(range(224, 256)), 128, 33, 0),
        (b"\xc8\xff", 2048, 9, 0),
        (b"\xc8" * 30 + b"\xff", 128, 11, 2),
        (b"\xc8\xff", 5, 9, 0),
    ],
)
def test_period_palette_minimizes_physical_pattern(
    pattern, repeats, payload, palette_size
):
    raw = pattern * repeats
    array = CompressedArray(raw, chunk_size=len(raw), cache_bytes=65536)
    info = array.storage_info()
    assert info.periodic_chunks == 1
    assert info.stored_bytes == payload
    assert array._chunks[0][1] == palette_size
    assert array.tobytes() == raw
    assert array.storage_info().cache_bytes == payload - 1
    array[len(pattern)] = 0
    expected = bytearray(raw)
    expected[len(pattern)] = 0
    assert array.tobytes() == expected
    array.clear_cache()
    assert array.tobytes() == expected
