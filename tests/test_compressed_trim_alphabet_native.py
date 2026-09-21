"""Exact span alphabets from trusted global colors and one membership query."""

import random

import pytest
from tightarray._core import _trim_plan


def exact_plan(raw, enabled, limit):
    """Independent oracle: enumerate endpoints and rebuild each span alphabet."""
    best = None
    for default in dict.fromkeys((raw[0], raw[-1])):
        indexes = [i for i, value in enumerate(raw) if value != default]
        if not indexes:
            continue
        start, stop = indexes[0], indexes[-1] + 1
        colors = bytes(sorted(set(raw[start:stop])))
        bits = max(1, colors[-1].bit_length())
        size = ((stop - start) * bits + 63) // 64 * 8
        palette = b""
        if enabled and len(colors) < 256:
            packed_bits = max(1, (len(colors) - 1).bit_length())
            packed_size = ((stop - start) * packed_bits + 63) // 64 * 8 + len(colors)
            if packed_size < size:
                bits, size, palette = packed_bits, packed_size, colors
        if size + 8 < limit:
            limit = size + 8
            best = default, start, stop, bits, palette, limit
    return best


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("color_count", [2, 3, 4, 5, 8, 9, 16, 17, 128, 129, 255, 256])
def test_default_presence_and_palette_boundaries(enabled, color_count):
    colors = bytes(range(256 - color_count, 256))
    left, right = colors[0], colors[-1]
    # Same/different endpoints; default absent, early, or late in the interior.
    for middle in (colors[1:] * 3, colors[:-1] * 3, colors * 3,
                   colors[1:] * 3 + colors[:1], colors[-1:] + colors[:-1] * 3):
        for end in (left, right):
            raw = bytes([left]) * 173 + middle + bytes([end]) * 157
            alphabet = bytes(sorted(set(raw)))
            for limit in (17, 24, 40, 128, len(raw), 100000):
                assert _trim_plan(raw, alphabet, enabled, limit) == exact_plan(
                    raw, enabled, limit
                )


def test_random_exact_span_alphabets():
    rng = random.Random(8217)
    for _ in range(250):
        palette = rng.sample(range(256), rng.randrange(2, 40))
        middle = bytes(rng.choices(palette, k=rng.randrange(1, 256)))
        raw = (bytes([rng.choice(palette)]) * rng.randrange(1, 180)
               + middle + bytes([rng.choice(palette)]) * rng.randrange(1, 180))
        colors = bytes(sorted(set(raw)))
        for enabled in (False, True):
            for limit in (32, len(raw), 100000):
                assert _trim_plan(raw, colors, enabled, limit) == exact_plan(
                    raw, enabled, limit
                )


def test_incomplete_trusted_metadata_remains_memory_safe():
    # Completeness is a private precondition, not a newly added validation rule.
    # Invalid metadata has no result-parity guarantee, but bounded output must
    # remain safe and existing shape/order validation still applies elsewhere.
    raw = b"\xff" * 120 + bytes(range(256)) + b"\xff" * 120
    for colors in (b"\x00\x01", b"\x00\xff", b"\x01\x02\x03"):
        result = _trim_plan(raw, colors, True, 100000)
        if result is not None:
            default, start, stop, bits, palette, size = result
            assert 0 <= default <= 255 and 0 <= start < stop <= len(raw)
            assert 1 <= bits <= 8 and len(palette) <= 256 and size <= 100000
