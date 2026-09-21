"""Native span writes prevalidate all bytes and preserve roots outside the span."""

import sys

import pytest
from tightarray._core import _SpanHot

from tightarray import Array


@pytest.mark.parametrize("bits", range(1, 9))
@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
@pytest.mark.parametrize("paletted", [False, True])
def test_view_write_roundtrip(bits, layout, paletted):
    values = bytes(i % (1 << bits) for i in range(100))
    root = Array(values, bits=bits, layout=layout)
    data = root[7:83]
    palette = bytes(reversed(range(1 << bits))) if paletted else b""
    hot = _SpanHot(data, palette, default=213, start=11, length=110)
    expected = bytearray(hot.read())
    root_expected = bytearray(values)
    for relative in (0, 3, 31, 60):
        codes = bytes((i + 1) % (1 << bits) for i in range(16))
        piece = bytes(palette[code] for code in codes) if palette else codes
        assert hot.try_write(11 + relative, piece) is True
        expected[11 + relative : 27 + relative] = piece
        root_expected[7 + relative : 23 + relative] = codes
        assert hot.read() == expected
        assert root.tobytes() == root_expected
        assert hot.dirty
        hot.dirty = False


@pytest.mark.parametrize("paletted", [False, True])
@pytest.mark.parametrize("dirty", [False, True])
def test_late_unrepresentable_does_not_mutate(paletted, dirty):
    hot = _SpanHot(
        Array(b"\0\x01\0\x01", bits=1),
        b"xy" if paletted else b"",
        default=9,
        start=2,
        length=8,
    )
    hot.dirty = dirty
    before = hot.read()
    piece = b"xyZ" if paletted else b"\x01\x00\x02"
    assert hot.try_write(3, piece) is False
    assert hot.read() == before
    assert hot.dirty is dirty


def test_outside_span_and_empty_writes():
    hot = _SpanHot(Array(b"ab"), default=0, start=2, length=6)
    for offset, piece in ((0, b"x"), (1, b"xy"), (3, b"xyz"), (4, b"x")):
        assert hot.try_write(offset, piece) is False
        assert hot.read() == b"\0\0ab\0\0"
        assert not hot.dirty
    for offset in range(7):
        assert hot.try_write(offset, b"") is True
        assert not hot.dirty
    hot.dirty = True
    assert hot.try_write(0, b"") is True
    assert hot.dirty
    empty = _SpanHot(Array(b""), default=7, start=0, length=0)
    assert empty.try_write(0, b"") is True


def test_duplicate_palette_first_fitting_code():
    hot = _SpanHot(Array(b"\0\x01", bits=1), b"xyx", default=0, start=0, length=2)
    assert hot.try_write(0, b"yx") is True
    assert hot.data.tobytes() == b"\x01\0"
    # A code existing only outside current width must not be truncated.
    other = _SpanHot(Array(b"\0\x01", bits=1), b"xyz", default=0, start=0, length=2)
    assert other.try_write(0, b"xz") is False
    assert other.data.tobytes() == b"\0\x01"
    assert not other.dirty


def test_input_validation_and_huge_logical_bound():
    class BytesSubclass(bytes):
        pass

    hot = _SpanHot(Array(b"x"), default=0, start=2, length=4)
    before = hot.read()
    for offset, piece in ((-1, b""), (5, b""), (4, b"x"), (sys.maxsize + 1, b"")):
        with pytest.raises(IndexError):
            hot.try_write(offset, piece)
    for piece in (None, "x", bytearray(b"x"), memoryview(b"x"), BytesSubclass(b"x")):
        with pytest.raises(TypeError):
            hot.try_write(2, piece)
    for offset in (None, 1.5, "2"):
        with pytest.raises(TypeError):
            hot.try_write(offset, b"x")
    assert hot.read() == before and not hot.dirty

    class Index:
        def __index__(self):
            return 2

    assert hot.try_write(Index(), b"y") is True
    huge = _SpanHot(Array(b"x"), default=0, start=sys.maxsize - 1, length=sys.maxsize)
    assert huge.try_write(sys.maxsize - 1, b"y") is True
    assert huge[-1] == ord("y")
    with pytest.raises(IndexError):
        huge.try_write(sys.maxsize - 1, b"yz")
