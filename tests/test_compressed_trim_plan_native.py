"""Native trim planner parity with the independently expressed Python policy."""

import random
import sys

import pytest
from tightarray._core import _trim_plan


def oracle(raw, colors, palette_enabled, limit):
    if not raw or len(colors) < 2 or len(raw) > 65535 or limit <= 16:
        return None
    bits = lambda value: max(1, value.bit_length())
    best = None
    for default in dict.fromkeys((raw[0], raw[-1])):
        changed = [i for i, value in enumerate(raw) if value != default]
        if not changed:
            continue
        first, last = changed[0], changed[-1] + 1
        if first == 0 and last == len(raw):
            continue
        length = last - first
        maximum = colors[-2] if default == colors[-1] else colors[-1]
        lower = ((length * bits(maximum) + 63) // 64) * 8
        if palette_enabled:
            lower = min(
                lower,
                len(colors) - 1 + ((length * bits(len(colors) - 2) + 63) // 64) * 8,
            )
        if 8 + lower >= limit:
            continue
        span_colors = bytes(sorted(set(raw[first:last])))
        width = bits(span_colors[-1])
        palette = b""
        size = ((length * width + 63) // 64) * 8
        if palette_enabled and len(span_colors) < 256:
            width_palette = bits(len(span_colors) - 1)
            size_palette = len(span_colors) + ((length * width_palette + 63) // 64) * 8
            if size_palette < size:
                width, palette, size = width_palette, span_colors, size_palette
        if 8 + size < limit:
            limit = 8 + size
            best = (default, first, last, width, palette, limit)
    return best


@pytest.mark.parametrize("palette_enabled", [False, True])
def test_adversarial_and_limits(palette_enabled):
    cases = [
        b"",
        b"\xff" * 99,
        bytes(range(256)),
        b"\0" * 50 + b"\xff" * 20 + b"\x01" * 50,
        b"\x01" * 200 + b"\xff\x80" * 15 + b"\x01" * 300,
        b"\xff" * 200 + b"\0\x01" * 15 + b"\xff" * 300,
        b"\0" * 65500 + b"\x03" * 35,
        b"\0" * 65500 + b"\x03" * 36,
    ]
    for raw in cases:
        colors = bytes(sorted(set(raw)))
        for limit in (-1, 0, 16, 17, 18, 24, 64, len(raw), sys.maxsize):
            assert _trim_plan(raw, colors, palette_enabled, limit) == oracle(
                raw, colors, palette_enabled, limit
            )


def test_random_oracle_all_widths():
    rng = random.Random(7722)
    for width in range(1, 9):
        for _ in range(70):
            a, b = rng.randrange(1 << width), rng.randrange(1 << width)
            middle = bytes(
                rng.randrange(1 << width) for _ in range(rng.randrange(1, 180))
            )
            raw = (
                bytes([a]) * rng.randrange(180)
                + middle
                + bytes([b]) * rng.randrange(180)
            )
            colors = bytes(sorted(set(raw)))
            for enabled in (False, True):
                limit = rng.choice((17, 32, 64, 128, len(raw), sys.maxsize))
                assert _trim_plan(raw, colors, enabled, limit) == oracle(
                    raw, colors, enabled, limit
                )


def test_validation_and_trusted_metadata_safety():
    for colors in (b"aa", b"\x02\x01", bytes(257)):
        with pytest.raises(ValueError):
            _trim_plan(b"aab", colors, True, 100)
    for raw, colors in ((bytearray(b"ab"), b"ab"), (b"ab", memoryview(b"ab"))):
        with pytest.raises(TypeError):
            _trim_plan(raw, colors, True, 100)
    for enabled in (None, 1, "yes"):
        with pytest.raises(TypeError):
            _trim_plan(b"ab", b"ab", enabled, 100)
    with pytest.raises(OverflowError):
        _trim_plan(b"ab", b"ab", True, sys.maxsize + 1)
    with pytest.raises(TypeError):
        _trim_plan(b"ab", b"ab", True, 3.2)
    # Incomplete but ordered private metadata may prune; it must remain safe.
    assert _trim_plan(b"\xff" * 20, b"\0\x01", True, 100) is None
    assert _trim_plan(b"abc", b"", True, 100) is None

    class Limit:
        def __index__(self):
            return 100

    raw = b"\0" * 40 + b"\x01" * 20 + b"\0" * 40
    assert _trim_plan(raw, b"\0\x01", True, Limit()) == oracle(
        raw, b"\0\x01", True, 100
    )
