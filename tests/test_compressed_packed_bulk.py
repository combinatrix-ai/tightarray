"""Codec-free bulk mutation preserves the cache and exact persisted values."""

import random

import pytest

from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("bits", range(1, 8))
@pytest.mark.parametrize("paletted", [False, True])
def test_cached_partial_writes_and_reload(bits, paletted):
    rng = random.Random(8320 + bits)
    low = 256 - (1 << bits) if paletted else 0
    expected = bytearray(rng.randrange(low, low + (1 << bits)) for _ in range(4096))
    array = CompressedArray(bytes(expected), codec="none", cache_bytes=65536)
    assert array[0] == expected[0]
    hot = array._cache[0]
    assert hot.data.bits == bits
    for count in (1, 8, 15, 16, 17, 63, 64, 65, 256, 513, 1024):
        for offset in (0, 1, 3, 7, 4096 - count):
            value = bytes(x ^ 1 for x in expected[offset : offset + count])
            array.write(offset, value)
            expected[offset : offset + count] = value
            assert array._cache[0] is hot
            assert array.tobytes() == expected
            assert hot.dirty
    array.flush()
    assert not hot.dirty
    array.clear_cache()
    assert array.tobytes() == expected


def test_cross_chunk_write_and_uncached_fallback():
    original = bytes(random.Random(8321).randbytes(8192))
    original = bytes(x & 31 for x in original)
    for budget in (0, 512, 65536):
        array = CompressedArray(original, codec="none", cache_bytes=budget)
        expected = bytearray(original)
        for start, count in ((4089, 513), (1, 1024), (7159, 1031)):
            value = bytes(x ^ 1 for x in expected[start : start + count])
            array.write(start, value)
            expected[start : start + count] = value
        array.flush()
        assert array.storage_info().cache_bytes <= budget
        array.clear_cache()
        assert array.tobytes() == expected
