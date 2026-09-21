"""Palette mapping is bounded and exact across native SIMD/block boundaries."""

import random
import sys

import pytest
from tightarray._core import _pack_bytes, _pack_palette


def oracle(codes, bits):
    value = sum(code << (index * bits) for index, code in enumerate(codes))
    return value.to_bytes(((len(codes) * bits + 63) // 64) * 8, "little")


@pytest.mark.parametrize("bits", range(1, 9))
def test_palette_blocks_tails_and_independent_oracle(bits):
    rng = random.Random(bits + 127)
    palette = bytes(sorted(rng.sample(range(256), 1 << bits)))
    for length in [*range(70), 127, 255, 511, 512, 513, 519, 1023, 1024, 1025, 4093]:
        codes = bytes(rng.randrange(len(palette)) for _ in range(length))
        raw = bytes(palette[code] for code in codes)
        result = _pack_palette(raw, bits, palette)
        assert result == oracle(codes, bits) == _pack_bytes(codes, bits)
        assert type(result) is bytes


@pytest.mark.parametrize("bits", range(1, 9))
def test_missing_value_every_position_and_late_blocks(bits):
    palette = bytes([100, 200])
    for length in (17, 513, 1025):
        for position in range(length):
            raw = bytearray([100] * length)
            raw[position] = 99
            with pytest.raises(ValueError, match="missing"):
                _pack_palette(bytes(raw), bits, palette)
            assert raw[position] == 99


def test_palette_contract_and_argument_types():
    class BytesSubclass(bytes):
        pass

    for palette in (b"", b"aa", b"ba", bytes(range(3))):
        with pytest.raises(ValueError):
            _pack_palette(b"", 1, palette)
    with pytest.raises(ValueError):
        _pack_palette(b"", 8, bytes(257))
    for value in (bytearray(b"a"), memoryview(b"a"), BytesSubclass(b"a"), "a", None):
        with pytest.raises(TypeError):
            _pack_palette(value, 1, b"a")
        with pytest.raises(TypeError):
            _pack_palette(b"a", 1, value)
    for bits in (-1, 0, 9):
        with pytest.raises(ValueError):
            _pack_palette(b"a", bits, b"a")
    for bits in (None, 1.0, "1"):
        with pytest.raises(TypeError):
            _pack_palette(b"a", bits, b"a")
    with pytest.raises(OverflowError):
        _pack_palette(b"a", sys.maxsize + 1, b"a")

    class Index:
        def __index__(self):
            return 1

    assert _pack_palette(b"a", Index(), b"a") == bytes(8)
    assert _pack_palette(b"", 8, bytes(range(256))) == b""
