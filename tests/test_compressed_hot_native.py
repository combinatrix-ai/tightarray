"""Native cache-entry ownership, views, palette validation and slice semantics."""

import gc
import sys

import pytest
from tightarray._core import _Hot

from tightarray import Array


@pytest.mark.parametrize("bits", range(1, 9))
@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
def test_read_and_view(bits, layout):
    values = bytes(i % (1 << bits) for i in range(150))
    source = Array(values, bits=bits, layout=layout)
    data = source[7:137]
    palette = bytes(reversed(range(1 << bits)))
    hot = _Hot(data, palette)
    expected = bytes(palette[value] for value in values[7:137])
    assert hot.data is data
    assert hot.palette is palette
    assert hot.nbytes == data.nbytes + len(palette)
    assert hot.read() == expected
    for start in (None, -200, -3, 0, 1, 60, 130, 1000):
        for stop in (None, -200, -1, 0, 13, 130, 1000):
            assert hot.read(start, stop) == expected[start:stop]
    assert hot.read(start=-3, stop=None) == expected[-3:]
    for index in range(-len(expected), len(expected)):
        assert hot[index] == expected[index]
    for bad in (-len(expected) - 1, len(expected), sys.maxsize + 1):
        with pytest.raises(IndexError):
            hot[bad]
    with pytest.raises(TypeError):
        hot[0:1]


def test_direct_mutation_and_strong_ownership():
    data = Array(bytes(range(32)), bits=5)
    hot = _Hot(data)
    before = sys.getrefcount(data)
    assert hot.read() == bytes(range(32))
    assert hot.nbytes == data.nbytes
    data[3] = 17
    assert hot[3] == 17
    del data
    gc.collect()
    assert hot[3] == 17
    assert before >= 3
    assert not hot.dirty
    hot.dirty = True
    assert hot.dirty
    hot.dirty = False
    for value in (1, None, "yes"):
        with pytest.raises(TypeError):
            hot.dirty = value
    with pytest.raises(TypeError):
        del hot.dirty
    with pytest.raises(AttributeError):
        hot.data = Array(b"")
    with pytest.raises(AttributeError):
        hot.palette = b""
    with pytest.raises(AttributeError):
        hot.extra = 1


def test_invalid_palette_codes_and_empty():
    hot = _Hot(Array(b"\x00\x01\x02", bits=2), b"ab")
    assert hot[0] == ord("a")
    assert hot.read(0, 2) == b"ab"
    with pytest.raises(ValueError):
        hot[2]
    with pytest.raises(ValueError):
        hot.read()
    assert hot.read(3) == b""
    empty = _Hot(Array(b""), b"x", True)
    assert empty.read() == b""
    assert empty.nbytes == empty.data.nbytes + 1
    with pytest.raises(IndexError):
        empty[0]


def test_constructor_validation():
    class BytesSubclass(bytes):
        pass

    for palette in (None, bytearray(b"x"), BytesSubclass(b"x"), bytes(257)):
        with pytest.raises(TypeError):
            _Hot(Array(b"\0"), palette)
    for data in (b"", [], None):
        with pytest.raises(TypeError):
            _Hot(data)
    with pytest.raises(TypeError):
        _Hot(Array(b""), dirty=1)


def test_read_index_protocol_and_errors():
    class Index:
        def __index__(self):
            return 1

    hot = _Hot(Array(b"\x02\x04\x06", bits=3))
    assert hot[Index()] == 4
    assert hot.read(Index()) == b"\x04\x06"
    with pytest.raises(TypeError):
        hot.read(1.5)
    with pytest.raises(TypeError):
        hot.read(stop="x")
