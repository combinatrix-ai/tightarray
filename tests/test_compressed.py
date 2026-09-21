"""Behavioral coverage for bounded-cache compressed uint8 arrays."""

import random

import pytest

from tightarray.compressed import CompressedArray


def assert_cache_bound(array):
    info = array.storage_info()
    assert info.cache_bytes <= info.cache_limit_bytes
    assert info.owned_bytes >= info.stored_bytes
    assert info.logical_bytes == len(array)


def test_partial_chunks_indexes_slices_and_independent_bytes():
    source = list(range(19))
    array = CompressedArray(source, chunk_size=8, cache_bytes=32)
    assert len(array) == 19
    assert array.storage_info().chunk_count == 3
    assert array[-1] == 18
    assert array[-19] == 0
    assert array[5:14] == bytes(source[5:14])
    assert array[::-2] == bytes(source[::-2])
    assert array[100:] == b""
    saved = array[5:14]
    array[7] = 255
    array[-1] = 200
    source[0] = 99
    assert saved == bytes(range(5, 14))
    assert array[0] == 0
    assert array.read(6, 10) == bytes([6, 255, 8, 9])
    assert array[-1] == 200
    with pytest.raises(IndexError):
        _ = array[19]
    with pytest.raises(IndexError):
        array[-20] = 1
    assert_cache_bound(array)


def test_zero_cache_cross_chunk_write_persists():
    array = CompressedArray.full(23, 0, chunk_size=8, cache_bytes=0)
    values = list(range(101, 117))
    array.write(5, iter(values))
    expected = bytes([0] * 5 + values + [0] * 2)
    assert array.tobytes() == expected
    assert array.storage_info().cache_bytes == 0
    array.flush()
    array.clear_cache()
    assert array.tobytes() == expected
    assert_cache_bound(array)


def test_dirty_eviction_writes_back_and_cache_observability():
    # One 64-byte full-width chunk fits; two cannot.
    array = CompressedArray(range(256), chunk_size=64, cache_bytes=64, palette=False)
    array[0] = 255
    after_first = array.storage_info()
    assert array[0] == 255
    assert array.storage_info().cache_hits > after_first.cache_hits
    array[64] = 254
    array[128] = 253
    assert_cache_bound(array)
    info = array.storage_info()
    assert info.evictions > 0
    assert info.cache_misses > 0
    array.clear_cache()
    assert array.storage_info().cache_bytes == 0
    expected = bytearray(range(256))
    expected[0], expected[64], expected[128] = 255, 254, 253
    assert array.tobytes() == bytes(expected)
    array.flush()
    array.flush()
    assert array.tobytes() == bytes(expected)


def test_uniform_palette_expansion_and_return_to_uniform():
    array = CompressedArray.full(256, 250, chunk_size=256, cache_bytes=128)
    assert array.storage_info().uniform_chunks == 1
    rng = random.Random(42)
    two_values = bytes(rng.choice((250, 251)) for _ in range(256))
    array.write(0, two_values)
    array.flush()
    array.clear_cache()
    assert array.storage_info().palette_chunks == 1
    assert array.tobytes() == two_values
    # Palette growth exceeds the original physical width and the hot budget.
    array.write(0, range(256))
    array.flush()
    array.clear_cache()
    assert array.tobytes() == bytes(range(256))
    assert_cache_bound(array)
    array.write(0, [7] * 256)
    array.flush()
    array.clear_cache()
    assert array.storage_info().uniform_chunks == 1
    assert array.tobytes() == bytes([7] * 256)


@pytest.mark.parametrize("invalid", [-1, 256, 1.5, "1", None])
def test_invalid_values_do_not_partially_modify(invalid):
    array = CompressedArray(range(20), chunk_size=4, cache_bytes=8)
    before = array.tobytes()
    with pytest.raises((TypeError, ValueError, OverflowError)):
        array.write(2, [100, 101, 102, 103, 104, invalid])
    assert array.tobytes() == before
    with pytest.raises((TypeError, ValueError, OverflowError)):
        array[3] = invalid
    assert array.tobytes() == before


def test_exhausted_generator_failure_before_mutation():
    array = CompressedArray(range(16), chunk_size=4, cache_bytes=4)

    def failing_values():
        yield 99
        yield 98
        raise RuntimeError("input generation failed")

    with pytest.raises(RuntimeError, match="input generation failed"):
        array.write(1, failing_values())
    assert array.tobytes() == bytes(range(16))


def test_explicit_read_and_write_bounds_are_validated():
    array = CompressedArray(range(10), chunk_size=3, cache_bytes=8)
    for start, stop in [(-1, 2), (2, 1), (0, 11), (11, 11)]:
        with pytest.raises((ValueError, IndexError)):
            array.read(start, stop)
    for start, values in [(-1, [1]), (9, [1, 2]), (11, [])]:
        with pytest.raises((ValueError, IndexError)):
            array.write(start, values)
        assert array.tobytes() == bytes(range(10))
    array.write(10, [])
    assert array.read(10, 10) == b""
    assert array.read() == bytes(range(10))


def test_empty_array_and_index_protocol():
    array = CompressedArray([], chunk_size=3, cache_bytes=0)
    assert array.tobytes() == b""
    assert array[::-1] == b""
    array.write(0, [])
    array.flush()
    array.clear_cache()
    assert array.storage_info().chunk_count == 0
    with pytest.raises(IndexError):
        _ = array[0]

    class Index:
        def __index__(self):
            return 9

    array = CompressedArray([Index()], chunk_size=2, cache_bytes=2)
    assert array[0] == 9
    array.write(0, [Index()])
    assert array.tobytes() == b"\x09"


@pytest.mark.parametrize("codec", ["lz4", "zstd"])
def test_optional_codecs_preserve_evicted_updates(codec):
    pytest.importorskip("blosc2")
    data = bytes(range(256)) * 4
    array = CompressedArray(data, chunk_size=256, cache_bytes=128, codec=codec)
    array.write(250, [255, 0, 17, 44, 89, 12, 5, 6, 7, 8])
    array.flush()
    array.clear_cache()
    expected = bytearray(data)
    expected[250:260] = bytes([255, 0, 17, 44, 89, 12, 5, 6, 7, 8])
    assert array.tobytes() == bytes(expected)
    assert_cache_bound(array)


@pytest.mark.parametrize(
    "kwargs",
    [{"chunk_size": 0}, {"chunk_size": -1}, {"cache_bytes": -1}, {"codec": "invalid"}],
)
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        CompressedArray([0], **kwargs)


@pytest.mark.parametrize("length,value", [(-1, 0), (1, -1), (1, 256)])
def test_full_rejects_invalid_shape_or_value(length, value):
    with pytest.raises((ValueError, OverflowError)):
        CompressedArray.full(length, value)


def fail_encoding(self, raw):
    raise RuntimeError("injected encoder failure")


@pytest.mark.parametrize("action", ["flush", "clear_cache", "evict"])
def test_failed_writeback_preserves_authoritative_dirty_cache(monkeypatch, action):
    array = CompressedArray(
        bytes(range(128)), chunk_size=64, cache_bytes=64, palette=False
    )
    array[0] = 255
    used = array.storage_info().cache_bytes
    with monkeypatch.context() as patch:
        patch.setattr(CompressedArray, "_encode", fail_encoding)
        with pytest.raises(RuntimeError, match="injected encoder failure"):
            if action == "evict":
                _ = array[64]
            else:
                getattr(array, action)()
        assert array[0] == 255
        assert array.storage_info().cache_bytes == used
        assert_cache_bound(array)
    array.clear_cache()
    assert array[0] == 255
    assert array[64] == 64


def test_failed_zero_cache_write_keeps_previous_cold_state(monkeypatch):
    array = CompressedArray(bytes(range(32)), chunk_size=16, cache_bytes=0)
    before = array.tobytes()
    with monkeypatch.context() as patch:
        patch.setattr(CompressedArray, "_encode", fail_encoding)
        with pytest.raises(RuntimeError, match="injected encoder failure"):
            array.write(3, [255, 254])
        assert array.tobytes() == before
        assert array.storage_info().cache_bytes == 0
    array[3] = 255
    assert array[3] == 255


def test_failed_oversized_growth_keeps_earlier_dirty_update(monkeypatch):
    array = CompressedArray.full(64, 0, chunk_size=64, cache_bytes=8, palette=False)
    array[0] = 1
    before = array.tobytes()
    with monkeypatch.context() as patch:
        patch.setattr(CompressedArray, "_encode", fail_encoding)
        with pytest.raises(RuntimeError, match="injected encoder failure"):
            array[1] = 255
        assert array.tobytes() == before
        assert_cache_bound(array)
    array.clear_cache()
    assert array.tobytes() == before
    array[1] = 255
    assert array[0] == 1
    assert array[1] == 255


def test_multichunk_codec_failure_keeps_completed_prefix_and_old_suffix(monkeypatch):
    array = CompressedArray.full(16, 0, chunk_size=8, cache_bytes=0)
    original = CompressedArray._encode
    calls = 0

    def fail_second(self, raw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second chunk failed")
        return original(self, raw)

    with monkeypatch.context() as patch:
        patch.setattr(CompressedArray, "_encode", fail_second)
        with pytest.raises(RuntimeError, match="second chunk failed"):
            array.write(0, range(16))
    # Cross-chunk codec failure intentionally is not an all-or-nothing transaction.
    assert array.tobytes() == bytes(range(8)) + bytes(8)
    array.write(8, range(8, 16))
    assert array.tobytes() == bytes(range(16))


def test_failed_decompression_does_not_poison_cache(monkeypatch):
    pytest.importorskip("blosc2")
    data = bytes(range(256)) * 32
    array = CompressedArray(data, chunk_size=4096, cache_bytes=4096, codec="zstd")
    assert array.storage_info().compressed_chunks > 0

    def fail_decompress(self, raw):
        raise RuntimeError("injected decoder failure")

    with monkeypatch.context() as patch:
        patch.setattr(CompressedArray, "_decompress", fail_decompress)
        with pytest.raises(RuntimeError, match="injected decoder failure"):
            array.read(100, 200)
        assert array.storage_info().cache_bytes == 0
    assert array.tobytes() == data


@pytest.mark.parametrize("cache_bytes", [0, 8, 128])
@pytest.mark.parametrize("palette", [False, True])
def test_mixed_operations_match_dense_reference(cache_bytes, palette):
    import random

    randomizer = random.Random(691)
    reference = bytearray(randomizer.randrange(256) for _ in range(97))
    array = CompressedArray(
        reference, chunk_size=17, cache_bytes=cache_bytes, palette=palette
    )
    for _ in range(80):
        operation = randomizer.randrange(5)
        if operation == 0:
            index, value = randomizer.randrange(97), randomizer.randrange(256)
            array[index] = value
            reference[index] = value
        elif operation == 1:
            start = randomizer.randrange(98)
            stop = randomizer.randrange(start, 98)
            values = bytes(randomizer.randrange(256) for _ in range(stop - start))
            array.write(start, values)
            reference[start:stop] = values
        elif operation == 2:
            array.flush()
        elif operation == 3:
            array.clear_cache()
        else:
            step = randomizer.choice([-3, -1, 1, 2])
            assert array[::step] == bytes(reference[::step])
        assert array.tobytes() == bytes(reference)
        assert_cache_bound(array)


def test_compressor_failure_preserves_dirty_data(monkeypatch):
    pytest.importorskip("blosc2")
    data = bytes(range(256)) * 4
    array = CompressedArray(data, chunk_size=1024, cache_bytes=1024, codec="zstd")
    array[0] = 254

    def fail_compress(self, raw, *, shuffle):
        raise RuntimeError("injected compressor failure")

    with monkeypatch.context() as patch:
        patch.setattr(CompressedArray, "_compress", fail_compress)
        with pytest.raises(RuntimeError, match="injected compressor failure"):
            array.flush()
        assert array[0] == 254
        assert_cache_bound(array)
    array.clear_cache()
    assert array.tobytes() == b"\xfe" + data[1:]


@pytest.mark.parametrize(
    "colors,new_value,cache_limit,maximum_hot",
    [(2, 202, 300, 259), (4, 204, 512, 389), (128, 1, 2048, 1024)],
)
def test_hot_palette_growth_keeps_small_representation(
    colors, new_value, cache_limit, maximum_hot
):
    first = 200 if colors < 128 else 128
    data = bytes(first + (index % colors) for index in range(1024))
    array = CompressedArray(
        data, chunk_size=1024, cache_bytes=cache_limit, palette=True
    )
    array[0] = new_value
    assert array.storage_info().cache_bytes > 0
    assert array.storage_info().cache_bytes <= maximum_hot
    assert array.tobytes() == bytes([new_value]) + data[1:]
    array.clear_cache()
    assert array.tobytes() == bytes([new_value]) + data[1:]
    assert_cache_bound(array)


def test_palette_growth_exceeding_tiny_cache_writes_through():
    data = bytes([250, 251]) * 512
    array = CompressedArray(data, chunk_size=1024, cache_bytes=130, palette=True)
    assert array[0] == 250
    array[0] = 252
    assert array.tobytes() == b"\xfc" + data[1:]
    assert_cache_bound(array)
    array.clear_cache()
    assert array.tobytes() == b"\xfc" + data[1:]


def test_none_codec_has_no_numpy_numba_or_blosc_dependency():
    import subprocess
    import sys

    script = """
import sys
from tightarray.compressed import CompressedArray
array = CompressedArray([250, 251] * 64, chunk_size=32, cache_bytes=32, codec='none')
array[0] = 252
array.write(31, [10, 20, 30])
array.flush()
array.clear_cache()
assert array[0] == 252
assert array.read(31, 34) == bytes([10, 20, 30])
assert len(array.tobytes()) == 128
loaded = {name.split('.')[0] for name in sys.modules}
assert not loaded.intersection({'numpy', 'numba', 'blosc2'}), loaded.intersection({'numpy', 'numba', 'blosc2'})
"""
    subprocess.run(
        [sys.executable, "-c", script], check=True, capture_output=True, text=True
    )
