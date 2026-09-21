"""Direct byte writes respect view offsets and leave root padding untouched."""

import pytest
from tightarray._core import _Hot, _SpanHot

from tightarray import Array


@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
@pytest.mark.parametrize("span", [False, True])
def test_nested_view_unaligned_copy_and_independent_source(layout, span):
    original = bytes((i * 31) % 256 for i in range(301))
    root = Array(original, bits=8, layout=layout)
    data = root[3:298][4:291]
    prefix = 13 if span else 0
    hot = (
        _SpanHot(data, default=239, start=prefix, length=len(data) + 27)
        if span
        else _Hot(data)
    )
    source = bytes(range(256))
    expected = bytearray(original)
    expected[12:268] = source
    assert hot.try_write(prefix + 5, source) is True
    assert root.tobytes() == expected
    assert hot.dirty
    assert source == bytes(range(256))
    # Source bytes remain separate from subsequent writes to the destination.
    assert hot.try_write(prefix + 5, b"\xff") is True
    assert source[0] == 0
    expected[12] = 255
    assert root.tobytes() == expected
    if span:
        assert hot.read(0, prefix) == bytes([239]) * prefix
        assert hot.read(prefix + len(data)) == bytes([239]) * 14


@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
@pytest.mark.parametrize("span", [False, True])
def test_tail_copy_preserves_physical_padding(layout, span):
    root = Array(bytes(range(19)), bits=8, layout=layout)
    # Nested view ends at the root's unaligned tail.
    data = root[1:][2:]
    prefix = 7 if span else 0
    hot = (
        _SpanHot(data, default=0, start=prefix, length=prefix + len(data))
        if span
        else _Hot(data)
    )
    before = bytes(root._word_view()[0])
    assert hot.try_write(prefix + len(data) - 3, b"\xff\x80\x00") is True
    expected = bytearray(before)
    expected[16:19] = b"\xff\x80\x00"
    assert bytes(root._word_view()[0]) == expected
    assert root.tobytes() == bytes(range(16)) + b"\xff\x80\x00"
    hot.dirty = False
    assert hot.try_write(prefix + len(data), b"") is True
    assert not hot.dirty
    with pytest.raises(IndexError):
        hot.try_write(prefix + len(data), b"x")
    assert bytes(root._word_view()[0]) == expected
