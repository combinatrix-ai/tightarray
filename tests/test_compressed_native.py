"""Private native chunk helpers: canonical bytes, validation, and ownership."""

import subprocess
import sys

import pytest
from tightarray._core import _byte_palette

from tightarray import Array


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\x00",
        b"\xff" * 1024,
        bytes(range(256)),
        bytes(range(255, -1, -1)) * 3,
        b"\xff\x80\x00\x80",
    ],
)
def test_palette(raw):
    assert _byte_palette(raw) == bytes(sorted(set(raw)))


@pytest.mark.parametrize("raw", [bytearray(b"a"), memoryview(b"a"), [1], "abc", 3])
def test_strict_bytes(raw):
    with pytest.raises(TypeError):
        _byte_palette(raw)
    with pytest.raises(TypeError):
        Array._from_packed_bytes(raw, 1, 1)


@pytest.mark.parametrize("bits", range(1, 9))
def test_restore(bits):
    for length in (0, 1, 2, 7, 8, 9, 21, 63, 64, 65, 129, 257):
        values = bytes((i * 73 + 17) % (1 << bits) for i in range(length))
        source = Array(values, bits=bits)
        raw = source._word_view()[0].tobytes()
        restored = Array._from_packed_bytes(raw, length, bits)
        assert restored.tobytes() == values
        assert restored.bits == bits
        assert restored.layout == "packed"
        assert restored.base is None
        assert restored._word_view()[0].tobytes() == raw
        if length:
            restored[0] = (restored[0] + 1) % (1 << bits)
            assert source.tobytes() == values
            assert raw == source._word_view()[0].tobytes()


@pytest.mark.parametrize("bits", range(1, 9))
def test_tail_canonicalization(bits):
    for length in (1, 7, 8, 63, 64, 65):
        words = (length * bits + 63) // 64
        restored = Array._from_packed_bytes(b"\xff" * (words * 8), length, bits)
        assert restored.tobytes() == bytes([(1 << bits) - 1]) * length
        expected = ((1 << (length * bits)) - 1).to_bytes(words * 8, "little")
        assert restored._word_view()[0].tobytes() == expected


@pytest.mark.parametrize(
    "raw,length,bits",
    [
        (b"", -1, 1),
        (b"", 0, 0),
        (b"", 0, 9),
        (b"", 1, 1),
        (b"\0" * 8, 0, 1),
        (b"\0" * 7, 1, 1),
        (b"\0" * 16, 1, 1),
    ],
)
def test_invalid_dimensions(raw, length, bits):
    with pytest.raises(ValueError):
        Array._from_packed_bytes(raw, length, bits)


def test_overflow_before_allocation():
    with pytest.raises((ValueError, OverflowError)):
        Array._from_packed_bytes(b"", sys.maxsize, 8)
    with pytest.raises(OverflowError):
        Array._from_packed_bytes(b"", sys.maxsize + 1, 1)
    with pytest.raises(OverflowError):
        Array._from_packed_bytes(b"", 1, sys.maxsize)


def test_no_numpy_dependency():
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from tightarray import Array; from tightarray._core import _byte_palette; "
                'assert _byte_palette(b"aab")==b"ab"; '
                "assert Array._from_packed_bytes(bytes(8),1,1).tobytes()==bytes(1); "
                'assert "numpy" not in sys.modules'
            ),
        ],
        check=True,
    )


@pytest.mark.parametrize("bits", range(1, 9))
def test_prefixed_restore(bits):
    for length in (0, 1, 8, 21, 64, 65):
        values = bytes((i * 43 + 9) % (1 << bits) for i in range(length))
        raw = Array(values, bits=bits)._word_view()[0].tobytes()
        for prefix in (b"", b"\xff", b"header\x00\x80"):
            sealed = prefix + raw
            restored = Array._from_packed_bytes(sealed, length, bits, len(prefix))
            assert restored.tobytes() == values
            assert restored.base is None
            if length:
                restored[0] = (restored[0] + 1) % (1 << bits)
                assert sealed == prefix + raw


def test_offset_tail_normalization():
    restored = Array._from_packed_bytes(b"abc" + b"\xff" * 8, 3, 5, 3)
    assert restored.tobytes() == b"\x1f" * 3
    assert restored._word_view()[0].tobytes() == b"\xff\x7f" + bytes(6)


@pytest.mark.parametrize("offset", [-1, 9, sys.maxsize])
def test_offset_outside_input(offset):
    with pytest.raises(ValueError):
        Array._from_packed_bytes(bytes(8), 0, 1, offset)


@pytest.mark.parametrize("offset", [1.0, "1", None])
def test_offset_not_index(offset):
    with pytest.raises(TypeError):
        Array._from_packed_bytes(bytes(8), 1, 1, offset)


def test_offset_index_and_exact_remaining_length():
    class Offset:
        def __index__(self):
            return 1

    assert Array._from_packed_bytes(b"x" + bytes(8), 1, 1, Offset()).tobytes() == bytes(
        1
    )
    assert Array._from_packed_bytes(b"x", 0, 1, Offset()).tobytes() == b""
    with pytest.raises(ValueError):
        Array._from_packed_bytes(b"x" + bytes(9), 1, 1, Offset())
    with pytest.raises(ValueError):
        Array._from_packed_bytes(b"x" + bytes(7), 1, 1, Offset())
    with pytest.raises(OverflowError):
        Array._from_packed_bytes(b"", 0, 1, sys.maxsize + 1)
