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
