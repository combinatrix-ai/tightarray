"""Native RLE candidate's strict size limit and malformed-input boundary."""

import sys

import pytest
from tightarray._core import _rle_decode, _rle_encode


@pytest.mark.parametrize(
    "length",
    [1, 2, 127, 128, 129, 254, 255, 256, 257, 511, 512, 513, 8193, 16384, 16385],
)
@pytest.mark.parametrize("value", [0, 127, 255])
def test_run_boundaries(length, value):
    raw = bytes([value]) * length
    encoded = _rle_encode(raw, sys.maxsize)
    remaining = length - 1
    parts = []
    while remaining >= 128:
        parts.append((remaining & 127) | 128)
        remaining >>= 7
    expected = bytes([*parts, remaining, value])
    assert encoded == expected
    assert _rle_decode(encoded, length) == raw
    assert _rle_encode(raw, len(encoded)) is None
    assert _rle_encode(raw, len(encoded) + 1) == encoded


def test_mixed_runs_and_early_limit():
    raw = bytes(range(256)) * 5
    encoded = _rle_encode(raw, len(raw) * 2 + 1)
    assert encoded == b"".join(bytes([0, value]) for value in raw)
    assert _rle_decode(encoded, len(raw)) == raw
    for limit in (-1, 0, 1, 2, 3, 10, len(raw), len(raw) * 2):
        assert _rle_encode(raw, limit) is None
    mixed = b"\x00" * 257 + b"\xff" * 255 + b"\x80" * 513 + b"z"
    result = _rle_encode(mixed, len(mixed))
    assert _rle_decode(result, len(mixed)) == mixed


def test_empty():
    assert _rle_encode(b"", 1) == b""
    assert _rle_encode(b"", sys.maxsize) == b""
    assert _rle_encode(b"", 0) is None
    assert _rle_encode(b"", -1) is None
    assert _rle_decode(b"", 0) == b""


@pytest.mark.parametrize(
    "payload,length",
    [
        (b"x", 1),
        (b"\x00xZ", 1),
        (b"", 1),
        (b"\x00x", 0),
        (b"\xff\x01x", 255),
        (b"\xff\x01x", 257),
        (b"", -1),
        (b"\xff\x01x" * 2, sys.maxsize),
    ],
)
def test_malformed(payload, length):
    with pytest.raises(ValueError):
        _rle_decode(payload, length)


@pytest.mark.parametrize("raw", [None, "abc", [1], bytearray(b"a"), memoryview(b"a")])
def test_strict_bytes(raw):
    with pytest.raises(TypeError):
        _rle_encode(raw, 10)
    with pytest.raises(TypeError):
        _rle_decode(raw, 1)


def test_integer_protocol_and_overflow():
    class Index:
        def __index__(self):
            return 3

    assert _rle_encode(b"aaa", Index()) == b"\x02a"
    assert _rle_decode(b"\x02a", Index()) == b"aaa"
    for bad in (1.5, None, "3"):
        with pytest.raises(TypeError):
            _rle_encode(b"a", bad)
        with pytest.raises(TypeError):
            _rle_decode(b"\x00a", bad)
    with pytest.raises(OverflowError):
        _rle_encode(b"a", sys.maxsize + 1)
    with pytest.raises(OverflowError):
        _rle_decode(b"", sys.maxsize + 1)


@pytest.mark.parametrize(
    "payload",
    [
        b"\x80",
        b"\x80\x01",
        b"\x80" * 20 + b"\x00x",
        b"\xff" * 10 + b"\x01x",
        b"\x00a\x80",
    ],
)
def test_truncated_or_overflowing_varint(payload):
    with pytest.raises(ValueError):
        _rle_decode(payload, 3)


@pytest.mark.parametrize("palette", [b"\xff\x00\x80", bytes(reversed(range(256)))])
def test_palette_run_encoding(palette):
    raw = bytes([palette[0]]) * 129 + bytes([palette[1]]) * 16385 + bytes([palette[2]])
    result = _rle_encode(raw, len(raw), palette)
    codes = _rle_decode(result, len(raw))
    assert codes == bytes(129) + b"\x01" * 16385 + b"\x02"
    assert bytes(palette[code] for code in codes) == raw
    assert _rle_encode(raw, len(result), palette) is None
    assert _rle_encode(raw, len(result) + 1, palette) == result


def test_empty_palette_is_identity():
    raw = b"\xff" * 257 + b"\x80" * 128
    assert _rle_encode(raw, 100, b"") == _rle_encode(raw, 100)
    assert _rle_encode(b"", 1, b"x") == b""


@pytest.mark.parametrize("palette", [b"aa", b"\x00\xff\x00"])
def test_duplicate_palette(palette):
    with pytest.raises(ValueError):
        _rle_encode(b"", 0, palette)


@pytest.mark.parametrize(
    "palette", [None, bytearray(b"x"), memoryview(b"x"), "x", bytes(257)]
)
def test_invalid_palette(palette):
    with pytest.raises(TypeError):
        _rle_encode(b"x", 100, palette)


def test_palette_unmapped_completed_run():
    with pytest.raises(ValueError):
        _rle_encode(b"a" * 128 + b"b", 100, b"a")
    # Early size rejection need not validate unvisited input values.
    assert _rle_encode(b"ab", 2, b"a") is None
