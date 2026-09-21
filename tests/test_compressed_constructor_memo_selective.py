import sys

import pytest

from benchmarks.compressed_constructor_memo_selective import (
    MISSING,
    ReservedMemo,
    pinned,
    selective_class,
)


def test_bound_and_resize_transitions():
    for budget in (1024, 1280, 1500, 2048, 4096, 8192, 65536):
        cache = ReservedMemo(budget)
        for n in range(400):
            key = n.to_bytes(4, "little") + b"x" * (n % 37)
            value = b"v" * (n % 63 + 1)
            cache.admit(key, value)
            assert cache.owned() <= budget
            for saved, record in cache.entries.items():
                assert cache.lookup(bytes(bytearray(saved))) == record
            independently_counted = (
                sys.getsizeof(cache)
                + sys.getsizeof(cache.entries)
                + sum(
                    sys.getsizeof(getattr(cache, name))
                    for name in cache.__slots__
                    if name != "entries"
                )
                + sum(
                    sys.getsizeof(k) + sys.getsizeof(v)
                    for k, v in cache.entries.items()
                )
            )
            assert independently_counted == cache.owned()
        assert cache.lookup(b"missing") is MISSING
        stats = cache.finish()
        assert stats["peak_retained_bytes"] <= budget
        assert not cache.entries


def test_uniform_bypass_and_shared_record_isolation():
    with pinned() as (base, hooked, _):
        cls = selective_class(hooked, 65536, base)
        raw = bytes(range(32)) * 128
        arr = cls(raw * 4, codec="zstd", chunk_size=4096)
        assert cls.last_memo["hits"] == 3
        assert arr._chunks[0] is arr._chunks[1]
        arr[0] = 255
        arr.flush()
        arr.clear_cache()
        assert arr.tobytes() == bytes([255]) + (raw * 4)[1:]
        assert not hasattr(arr, "_constructor_memo")
        uniform = cls(bytes(4096 * 4), codec="zstd", chunk_size=4096)
        assert cls.last_memo["misses"] == 0
        assert cls.last_memo["admissions"] == 0
        assert uniform.tobytes() == bytes(4096 * 4)
        plain = cls(raw, codec="none")
        assert type(plain) is base
        assert cls.last_memo is None


def test_constructor_failure_clears_cache():
    class Failing:
        def __init__(self, *args, **kwargs):
            type(self).captured = self._constructor_memo
            self._constructor_memo.admit(b"key", b"value")
            raise RuntimeError("injected")

    cls = selective_class(Failing, 65536, Failing)
    with pytest.raises(RuntimeError, match="injected"):
        cls(codec="zstd")
    assert not cls.captured.entries


def test_unexpected_mapping_reservation_overflow_rolls_back():
    class UnexpectedMetadata(ReservedMemo):
        __slots__ = ()

        def owned(self):
            actual = super().owned()
            return actual + (8192 if len(self.entries) >= 2 else 0)

    cache = UnexpectedMetadata(8192)
    cache.admit(b"first", b"a")
    cache.admit(b"second", b"b")
    assert cache.closed
    assert cache.entries == {b"first": b"a"}
    assert cache.owned() <= cache.budget
