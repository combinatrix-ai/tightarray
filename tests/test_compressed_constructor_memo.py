import pytest

from benchmarks.compressed_constructor_memo import MISSING, Memo, memo_class, pinned


def test_budget_and_exact_equality():
    memo = Memo(2048)
    for i in range(100):
        key = bytes([i]) * 100
        assert memo.lookup(key) is MISSING
        memo.admit(key, bytes([i]) * 40)
        assert memo.owned(memo.entries) <= 2048
    for key, value in memo.entries.items():
        assert memo.lookup(bytes(bytearray(key))) == value
    stats = memo.finish()
    assert stats["closed"] and stats["peak_retained_bytes"] <= 2048
    assert not memo.entries


def test_constructor_sharing_and_cleanup():
    with pinned() as (base, _):
        cls = memo_class(base, 65536)
        raw = (bytes(range(32)) * 128) * 4
        a = cls(raw, chunk_size=4096)
        assert cls.last_memo["hits"] == 3
        assert not hasattr(a, "_constructor_memo")
        assert a._chunks[0] is a._chunks[1]
        a[0] = 255
        a.flush()
        a.clear_cache()
        assert a.tobytes() == b"\xff" + raw[1:]
        assert cls.last_memo["hits"] == 3


def test_failure_clears_cache():
    captured = []

    class Failing:
        def __init__(self, values):
            captured.append(self._constructor_memo)
            self._encode(b"abc")
            raise RuntimeError("failure")

        def _encode(self, raw):
            return raw + b"record"

    cls = memo_class(Failing, 65536)
    with pytest.raises(RuntimeError):
        cls([])
    assert not captured[0].entries
