"""Packed bulk updates keep validation atomic and preserve every edge bit."""

import random

import pytest
from tightarray._core import _Hot, _SpanHot

from tightarray import Array


@pytest.mark.parametrize("bits", range(1, 9))
@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
@pytest.mark.parametrize("paletted", [False, True])
def test_all_edges_views_and_block_tails(bits, layout, paletted):
    rng = random.Random(bits)
    original = bytes(rng.randrange(1 << bits) for _ in range(1201))
    palette = bytes(reversed(range(1 << bits))) if paletted else b""
    for start in range(8):
        root = Array(original, bits=bits, layout=layout)
        data = root[1:1200][start:]
        hot = _Hot(data, palette)
        expected = bytearray(original)
        for offset in (0, 1, 3, 7):
            for count in (1, 7, 8, 15, 16, 17, 63, 64, 65, 511, 512, 513, 1031):
                codes = bytes(rng.randrange(1 << bits) for _ in range(count))
                raw = bytes(palette[x] for x in codes) if palette else codes
                assert hot.try_write(offset, raw)
                expected[1 + start + offset : 1 + start + offset + count] = codes
                assert root.tobytes() == expected
                # Exact physical comparison covers word gaps and tail padding.
                oracle = Array(bytes(expected), bits=bits, layout=layout)
                assert bytes(root._word_view()[0]) == bytes(oracle._word_view()[0])


@pytest.mark.parametrize("span", [False, True])
@pytest.mark.parametrize("palette", [False, True])
def test_late_invalid_cannot_mutate_head_or_first_block(span, palette):
    data = Array(bytes([1]) * 1100, bits=3)
    colors = bytes(range(128, 136)) if palette else b""
    hot = (
        _SpanHot(data, colors, default=0, start=3, length=1105)
        if span
        else _Hot(data, colors)
    )
    offset = 4 if span else 1
    before = hot.read()
    for position in (0, 7, 15, 511, 512, 1024):
        raw = bytearray([128 if palette else 0] * 1031)
        raw[position] = 255
        assert hot.try_write(offset, bytes(raw)) is False
        assert hot.read() == before and not hot.dirty


def test_duplicate_palette_first_fitting_and_span_success():
    data = Array(bytes(1100), bits=1)
    hot = _SpanHot(data, b"aba", default=255, start=3, length=1110)
    raw = b"ba" * 515 + b"b"
    assert hot.try_write(4, raw)
    assert hot.read(4, 1035) == raw
    assert hot.read(0, 3) == b"\xff" * 3
    assert data[0] == 0 and data[1032] == 0
