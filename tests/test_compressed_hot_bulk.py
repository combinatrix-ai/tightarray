"""Ordinary cached partial writes retain capacity until cold re-encoding."""

import random

import pytest

import tightarray.compressed as live


def fail(*args):
    raise RuntimeError("injected failure")


def make_array(palette=False, budget=4096):
    rng = random.Random(2281)
    colors = (128, 255) if palette else tuple(range(32))
    raw = bytes(rng.choice(colors) for _ in range(512))
    array = live.CompressedArray(raw, chunk_size=512, cache_bytes=budget)
    hot = array._get_hot(0)
    assert not hot.repeated
    assert bool(hot.palette) is palette
    return array, hot, bytearray(raw)


@pytest.mark.parametrize("palette", [False, True])
def test_identity_flush_failure_and_reload(palette, monkeypatch):
    array, hot, expected = make_array(palette)
    size = array.storage_info().cache_bytes
    piece = b"\xff\x80" * 8 if palette else bytes(range(16))
    with monkeypatch.context() as patch:
        patch.setattr(array, "_make_hot", fail)
        array.write(19, piece)
    expected[19:35] = piece
    assert array._cache[0] is hot and hot.dirty
    assert array.storage_info().cache_bytes == size
    with monkeypatch.context() as patch:
        patch.setattr(array, "_encode", fail)
        with pytest.raises(RuntimeError):
            array.clear_cache()
    assert array._cache[0] is hot and hot.dirty
    assert array.tobytes() == expected
    array.clear_cache()
    assert array.tobytes() == expected


@pytest.mark.parametrize("palette", [False, True])
def test_growth_failure_atomic_and_success(palette, monkeypatch):
    array, hot, expected = make_array(palette)
    piece = bytes([128 if palette else 1, 99])
    with monkeypatch.context() as patch:
        patch.setattr(array, "_make_hot", fail)
        with pytest.raises(RuntimeError):
            array.write(7, piece)
    assert array.tobytes() == expected and not hot.dirty
    array.write(7, piece)
    expected[7:9] = piece
    assert array.tobytes() == expected


@pytest.mark.parametrize("budget", [0, 1])
def test_uncached_encode_failure(budget, monkeypatch):
    array, _, expected = make_array(budget=budget)
    monkeypatch.setattr(array, "_encode", fail)
    with pytest.raises(RuntimeError):
        array.write(7, b"\x01\x02")
    assert array.tobytes() == expected and not array._cache


def test_remove_only_max_retains_hot_width_then_reencodes():
    rng = random.Random(61)
    raw = bytearray(rng.randrange(8) for _ in range(512))
    raw[21] = 255
    array = live.CompressedArray(raw, chunk_size=512, palette=False)
    hot = array._get_hot(0)
    assert hot.data.bits == 8 and not hot.repeated
    array.write(21, b"\x03")
    raw[21] = 3
    assert array._cache[0] is hot and hot.data.bits == 8
    array.clear_cache()
    assert array.tobytes() == raw
    assert array._get_hot(0).data.bits == 3


def test_dirty_eviction_and_full_chunk_replacement():
    array, hot, expected = make_array(budget=320)
    original = bytes(expected)
    # Two chunks, only one hot chunk fits in cache.
    array = live.CompressedArray(original * 2, chunk_size=512, cache_bytes=320)
    hot = array._get_hot(0)
    array.write(5, b"\x01\x02")
    expected[5:7] = b"\x01\x02"
    array._get_hot(1)
    assert 0 not in array._cache and not hot.dirty
    assert array.read(0, 512) == expected
    array.write(0, bytes(512))
    assert array.read(0, 512) == bytes(512)
    assert array.read(512, 1024) == original
