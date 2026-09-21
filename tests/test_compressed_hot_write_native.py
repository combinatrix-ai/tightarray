"""Native ordinary hot writes prevalidate all bytes and preserve roots outside the span."""

import pytest
from tightarray._core import _Hot

from tightarray import Array


@pytest.mark.parametrize("bits", range(1, 9))
@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
@pytest.mark.parametrize("paletted", [False, True])
def test_view_write_roundtrip(bits, layout, paletted):
    values = bytes(i % (1 << bits) for i in range(100))
    root = Array(values, bits=bits, layout=layout)
    data = root[7:83]
    palette = bytes(reversed(range(1 << bits))) if paletted else b""
    hot = _Hot(data, palette)
    expected = bytearray(hot.read())
    root_expected = bytearray(values)
    for relative in (0, 3, 31, 60):
        codes = bytes((i + 1) % (1 << bits) for i in range(16))
        piece = bytes(palette[code] for code in codes) if palette else codes
        assert hot.try_write(relative, piece) is True
        expected[relative : 16 + relative] = piece
        root_expected[7 + relative : 23 + relative] = codes
        assert hot.read() == expected
        assert root.tobytes() == root_expected
        assert hot.dirty
        hot.dirty = False


@pytest.mark.parametrize("paletted", [False, True])
@pytest.mark.parametrize("dirty", [False, True])
def test_late_unrepresentable_does_not_mutate(paletted, dirty):
    hot = _Hot(
        Array(b"\0\x01\0\x01", bits=1),
        b"xy" if paletted else b"",
    )
    hot.dirty = dirty
    before = hot.read()
    piece = b"xyZ" if paletted else b"\x01\x00\x02"
    assert hot.try_write(1, piece) is False
    assert hot.read() == before
    assert hot.dirty is dirty


def test_periodic_empty_bounds_and_types():
    import sys

    class BytesSubclass(bytes):
        pass

    hot = _Hot(Array(b"ab"), length=sys.maxsize)
    assert hot.try_write(sys.maxsize, b"") is True
    assert hot.try_write(1, b"a") is False
    assert hot.data.tobytes() == b"ab" and not hot.dirty
    for offset, raw in ((-1, b""), (sys.maxsize + 1, b""), (sys.maxsize, b"x")):
        with pytest.raises(IndexError):
            hot.try_write(offset, raw)
    for raw in (bytearray(b"x"), memoryview(b"x"), BytesSubclass(b"x"), None):
        with pytest.raises(TypeError):
            hot.try_write(0, raw)
    with pytest.raises(TypeError):
        hot.try_write(1.5, b"x")
    empty = _Hot(Array(b""))
    assert empty.try_write(0, b"") is True
    assert not empty.dirty
    hot.dirty = True
    assert hot.try_write(0, b"") is True and hot.dirty


def test_duplicate_palette_and_index_protocol():
    class Index:
        def __index__(self):
            return 0

    hot = _Hot(Array(b"\0\x01", bits=1), b"xyx")
    assert hot.try_write(Index(), b"yx") is True
    assert hot.data.tobytes() == b"\x01\0"
    other = _Hot(Array(b"\0\x01", bits=1), b"xyz")
    assert other.try_write(0, b"xz") is False
    assert other.data.tobytes() == b"\0\x01" and not other.dirty
