"""Native trimmed-span cache views and logical bounds against dense bytes."""

import gc
import sys

import pytest
from tightarray._core import _SpanHot

from tightarray import Array


@pytest.mark.parametrize("bits", range(1, 9))
@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
def test_views_slices_and_palette(bits, layout):
    values = bytes((i * 71 + 9) % (1 << bits) for i in range(100))
    root = Array(values, bits=bits, layout=layout)
    data = root[7:83]
    palette = bytes(reversed(range(1 << bits)))
    hot = _SpanHot(data, palette, default=213, start=11, length=110)
    expected = (
        bytes([213]) * 11 + bytes(palette[x] for x in values[7:83]) + bytes([213]) * 23
    )
    assert hot.data is data and hot.palette is palette
    assert hot.start == 11 and hot.length == 110 and hot.default == 213
    assert hot.nbytes == data.nbytes + len(palette)
    assert hot.repeated
    assert hot.read() == expected
    for index in range(-110, 110):
        assert hot[index] == expected[index]
    for start in (None, -1000, -100, -5, 0, 10, 11, 13, 86, 87, 109, 110, 1000):
        for stop in (None, -1000, -2, 0, 11, 12, 83, 87, 110, 1000):
            assert hot.read(start, stop) == expected[start:stop]
    for index in (-111, 110, sys.maxsize + 1):
        with pytest.raises(IndexError):
            hot[index]
    with pytest.raises(TypeError):
        hot[:]


def test_empty_full_and_end_spans():
    for length in (0, 1, 100):
        for start in (0, length):
            hot = _SpanHot(Array(b""), default=255, start=start, length=length)
            assert hot.read() == b"\xff" * length
            assert hot.read(length) == b""
    for start, length in ((0, 3), (0, 7), (4, 7)):
        hot = _SpanHot(Array(b"abc"), default=7, start=start, length=length)
        assert hot.read() == bytes([7]) * start + b"abc" + bytes([7]) * (
            length - start - 3
        )
    hot = _SpanHot(Array(b"x"), default=0, start=sys.maxsize - 1, length=sys.maxsize)
    assert hot[-1] == ord("x")
    assert hot.read(sys.maxsize - 2) == b"\0x"
    assert hot.read(sys.maxsize) == b""


def test_mutation_ownership_and_metadata():
    data = Array(b"\0\x01", bits=1)
    hot = _SpanHot(data, b"xy", default=9, start=1, length=4)
    data[1] = 0
    del data
    gc.collect()
    assert hot.read() == b"\txx\t"
    assert not hot.dirty
    hot.dirty = True
    assert hot.dirty
    hot.dirty = False
    for attr in ("data", "palette", "default", "start", "length", "repeated", "nbytes"):
        with pytest.raises(AttributeError):
            setattr(hot, attr, None)
    with pytest.raises(AttributeError):
        hot.extra = 1
    for value in (1, None, "yes"):
        with pytest.raises(TypeError):
            hot.dirty = value
    with pytest.raises(TypeError):
        del hot.dirty


def test_palette_error_only_inside_overlap():
    hot = _SpanHot(Array(b"\x00\x02", bits=2), b"ab", default=200, start=2, length=6)
    assert hot[0] == 200
    assert hot[2] == 97
    assert hot.read(0, 3) == b"\xc8\xc8a"
    assert hot.read(4) == b"\xc8\xc8"
    assert hot.read(3, 3) == b""
    with pytest.raises(ValueError):
        hot[3]
    with pytest.raises(ValueError):
        hot.read()


@pytest.mark.parametrize(
    "start,length", [(-1, 3), (0, -1), (4, 3), (2, 3), (sys.maxsize, sys.maxsize)]
)
def test_span_bounds(start, length):
    with pytest.raises(ValueError):
        _SpanHot(Array(b"aa"), default=0, start=start, length=length)


def test_constructor_types_and_index_protocol():
    class Index:
        def __index__(self):
            return 2

    hot = _SpanHot(Array(b"x"), default=Index(), start=Index(), length=4)
    assert hot[Index()] == 120
    assert hot.read(Index()) == b"x\x02"
    for value in (-1, 256):
        with pytest.raises(ValueError):
            _SpanHot(Array(b""), default=value, start=0, length=0)
    for field in ("default", "start", "length"):
        for bad in (None, 1.5, "1"):
            kwargs = {"default": 0, "start": 0, "length": 0, field: bad}
            with pytest.raises(TypeError):
                _SpanHot(Array(b""), **kwargs)
        kwargs = {"default": 0, "start": 0, "length": 0, field: sys.maxsize + 1}
        with pytest.raises(OverflowError):
            _SpanHot(Array(b""), **kwargs)
    for data in (None, b"", []):
        with pytest.raises(TypeError):
            _SpanHot(data, default=0, start=0, length=0)

    class BytesSubclass(bytes):
        pass

    for palette in (None, bytearray(b"a"), BytesSubclass(b"a"), bytes(257)):
        with pytest.raises(TypeError):
            _SpanHot(Array(b""), palette, default=0, start=0, length=0)
    with pytest.raises(TypeError):
        _SpanHot(Array(b""))
    with pytest.raises(TypeError):
        _SpanHot(Array(b""), b"", 0, 0, 0)
    with pytest.raises(TypeError):
        hot.read(start=1.5)
