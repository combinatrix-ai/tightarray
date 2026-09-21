"""Native byte packing matches independent bit placement and Array payloads."""

import random
import sys

import pytest
from tightarray._core import _pack_bytes

from tightarray import Array


def oracle(raw, bits):
    value = sum(byte << (index * bits) for index, byte in enumerate(raw))
    return value.to_bytes(((len(raw) * bits + 63) // 64) * 8, "little")


@pytest.mark.parametrize("bits", range(1, 9))
def test_all_short_lengths_and_large_tails(bits):
    rng = random.Random(793 + bits)
    for length in [*range(130), 255, 256, 257, 4093, 4096, 4097]:
        raw = bytes(rng.randrange(1 << bits) for _ in range(length))
        result = _pack_bytes(raw, bits)
        assert type(result) is bytes
        assert result == oracle(raw, bits)
        assert result == bytes(Array(raw, bits=bits)._word_view()[0])
        assert Array._from_packed_bytes(result, length, bits).tobytes() == raw
        if bits == 8 and length % 8 == 0:
            assert result is raw


@pytest.mark.parametrize("bits", range(1, 8))
@pytest.mark.parametrize("length", [1, 7, 8, 15, 16, 17, 63, 4097])
def test_invalid_last_value_and_input_preservation(bits, length):
    raw = bytes(length - 1) + bytes([1 << bits])
    with pytest.raises(ValueError, match="outside bit width"):
        _pack_bytes(raw, bits)
    assert raw == bytes(length - 1) + bytes([1 << bits])


def test_types_index_bounds_and_independent_storage():
    class Subclass(bytes):
        pass

    class Index:
        def __index__(self):
            return 3

    assert _pack_bytes(b"\x07", Index()) == b"\x07" + bytes(7)
    for raw in (Subclass(b"a"), bytearray(b"a"), memoryview(b"a"), "a", None):
        with pytest.raises(TypeError):
            _pack_bytes(raw, 8)
    for bits in (0, -1, 9):
        with pytest.raises(ValueError):
            _pack_bytes(b"", bits)
    with pytest.raises(OverflowError):
        _pack_bytes(b"", sys.maxsize + 1)
    for bits in (1.5, "3", None):
        with pytest.raises(TypeError):
            _pack_bytes(b"", bits)
    payload = _pack_bytes(b"\x01\x02\x03", 2)
    restored = Array._from_packed_bytes(payload, 3, 2)
    restored[0] = 0
    assert payload == b"\x39" + bytes(7)
