"""Cached interior bulk updates preserve storage and failure boundaries."""

import random

import pytest

import tightarray.compressed as live
from tightarray import Array


def make_array(palette=False, budget=4096):
    rng = random.Random(2322)
    alphabet = (128, 255) if palette else tuple(range(32))
    inside = bytes(rng.choice(alphabet) for _ in range(100))
    raw = bytes(200) + inside + bytes(200)
    array = live.CompressedArray(raw, chunk_size=len(raw), cache_bytes=budget)
    hot = array._get_hot(0)
    assert isinstance(hot, live._span_entry_type)
    return array, hot, bytearray(raw)


def fail(*_args):
    raise RuntimeError("injected failure")


@pytest.mark.parametrize("palette", [False, True])
def test_cached_bulk_keeps_entry_and_flushes(palette, monkeypatch):
    array, hot, expected = make_array(palette)
    before = array.storage_info().cache_bytes
    piece = bytes([255, 128] * 8) if palette else bytes(range(16))
    for relative in (0, 7, len(hot.data) - len(piece)):
        offset = hot.start + relative
        with monkeypatch.context() as patch:
            patch.setattr(array, "_make_hot", fail)
            array.write(offset, piece)
        expected[offset : offset + len(piece)] = piece
        assert array._cache[0] is hot
        assert hot.dirty
        assert array.storage_info().cache_bytes == before
        assert array.tobytes() == expected
    with monkeypatch.context() as patch:
        patch.setattr(array, "_encode", fail)
        with pytest.raises(RuntimeError):
            array.flush()
        assert array._cache[0] is hot and hot.dirty
        assert array.tobytes() == expected
    array.clear_cache()
    assert array.tobytes() == expected


@pytest.mark.parametrize("palette", [False, True])
@pytest.mark.parametrize("cross_boundary", [False, True])
def test_failed_fallback_does_not_partially_write(palette, cross_boundary, monkeypatch):
    array, hot, expected = make_array(palette)
    offset = hot.start + len(hot.data) - 2 if cross_boundary else hot.start + 7
    valid = 128 if palette else 1
    piece = bytes([valid, valid, valid if cross_boundary else 99])
    monkeypatch.setattr(array, "_make_hot", fail)
    with pytest.raises(RuntimeError):
        array.write(offset, piece)
    assert array._cache[0] is hot
    assert not hot.dirty
    assert array.tobytes() == expected


@pytest.mark.parametrize("budget", [0, 1])
def test_uncached_failure_preserves_cold(budget, monkeypatch):
    array, hot, expected = make_array(True, budget)
    assert not array._cache
    monkeypatch.setattr(array, "_encode", fail)
    with pytest.raises(RuntimeError):
        array.write(hot.start + 5, b"\xff\x80\xff")
    assert not array._cache
    assert array.tobytes() == expected


def test_late_invalid_input_and_bounds_before_mutation():
    array, hot, expected = make_array()

    def broken():
        yield 1
        raise RuntimeError("injected failure")

    for values, error in (([1, 2, 256], ValueError), (broken(), RuntimeError)):
        with pytest.raises(error):
            array.write(hot.start, values)
        assert array.tobytes() == expected
        assert not hot.dirty
    with pytest.raises(IndexError):
        array.write(len(array) - 1, b"abc")
    assert array.tobytes() == expected


def test_native_view_late_invalid_is_atomic():
    root = Array(bytes(range(8)) * 8, bits=3)
    view = root[5:40]
    before = root.tobytes()
    with pytest.raises(ValueError):
        view._view_assign((4,), (1,), 17, b"\x01\x02\x03\x08")
    assert root.tobytes() == before
    view._view_assign((4,), (1,), 17, b"\x01\x02\x03\x07")
    expected = bytearray(before)
    expected[22:26] = b"\x01\x02\x03\x07"
    assert root.tobytes() == expected


def test_periodic_hot_still_materializes(monkeypatch):
    raw = b"\x01\x02" * 200
    array = live.CompressedArray(raw, chunk_size=len(raw))
    hot = array._get_hot(0)
    assert hot.repeated and not isinstance(hot, live._span_entry_type)
    monkeypatch.setattr(array, "_make_hot", fail)
    with pytest.raises(RuntimeError):
        array.write(7, b"\x02\x02")
    assert array.tobytes() == raw


def test_multichunk_failure_preserves_committed_prefix(monkeypatch):
    rng = random.Random(211)
    chunk = bytes(200) + bytes(rng.randrange(1, 32) for _ in range(100))
    array = live.CompressedArray(chunk * 2, chunk_size=300, cache_bytes=4096)
    first = array._get_hot(0)
    second = array._get_hot(1)
    assert isinstance(first, live._span_entry_type)
    assert isinstance(second, live._span_entry_type)
    monkeypatch.setattr(array, "_make_hot", fail)
    with pytest.raises(RuntimeError):
        array.write(290, bytes([1]) * 20)
    expected = bytearray(chunk * 2)
    expected[290:300] = bytes([1]) * 10
    assert array.tobytes() == expected
    assert array._cache[0] is first and first.dirty
    assert array._cache[1] is second and not second.dirty
