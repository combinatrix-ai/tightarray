"""Scalar hit dispatch must preserve LRU order and dirty authority."""

from tightarray.compressed import CompressedArray


def test_scalar_hits_protect_most_recent_chunk_from_eviction():
    values = bytes([0, 1] * 96)
    array = CompressedArray(values, chunk_size=64, cache_bytes=16)
    assert [array[i] for i in [0, 64, 0, 128]] == [0, 0, 0, 0]
    info = array.storage_info()
    assert (info.cache_hits, info.cache_misses, info.evictions) == (1, 3, 1)
    assert array[0] == 0
    assert array.storage_info().cache_misses == 3
    assert array[64] == 0
    assert array.storage_info().cache_misses == 4


def test_hot_dirty_value_overrides_uniform_cold_scalar():
    array = CompressedArray.full(128, 7, chunk_size=64, cache_bytes=64)
    assert array[3] == 7
    assert array.storage_info().cache_hits == 0
    assert array.storage_info().cache_misses == 0
    array[3] = 255
    assert array[3] == 255
    assert array[-125] == 255
    assert array[4] == 7
    array.clear_cache()
    assert array[3] == 255
    assert array[4] == 7
