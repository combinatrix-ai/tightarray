"""A selected exact period dominates any endpoint-trimmed packed span."""

import itertools
import random

from tightarray import _core


def check(raw, palette):
    colors = bytes(sorted(set(raw)))
    if len(colors) < 2:
        return
    period = _core._byte_period(raw)
    assert period and len(raw) >= 2 * period
    bits = max(1, colors[-1].bit_length())
    pbits = max(1, (len(colors) - 1).bit_length())
    packed = lambda size, width: ((size * width + 63) // 64) * 8
    size = packed(period, bits) + 1
    full = min(packed(len(raw), bits), len(raw))
    if palette and pbits < bits:
        size = min(size, packed(period, pbits) + 1 + len(colors))
        full = min(full, packed(len(raw), pbits) + len(colors))
    if size >= full:
        return
    for default in dict.fromkeys((raw[0], raw[-1])):
        positions = [i for i, value in enumerate(raw) if value != default]
        span = raw[positions[0] : positions[-1] + 1]
        assert len(span) >= period + 1
        assert bytes(sorted(set(span))) == colors
    assert _core._trim_plan(raw, colors, palette, size + 2) is None


def test_exhaustive_small_periods_and_partial_tails():
    for length in range(1, 7):
        for values in itertools.product((0, 128, 255), repeat=length):
            pattern = bytes(values)
            for tail in range(length):
                raw = pattern * 2 + pattern[:tail]
                check(raw, False)
                check(raw, True)


def test_large_periods_palette_boundaries_and_repetitions():
    rng = random.Random(1181)
    for length in (9, 31, 32, 63, 64, 127, 128, 251, 256):
        for states in (2, 3, 7, 8, 9, 15, 16, 17, 31, 32, 33, 128, 256):
            pattern = bytes(rng.randrange(256 - states, 256) for _ in range(length))
            for repeats in (2, 3, 16):
                for tail in (0, 1, length - 1):
                    for palette in (False, True):
                        check(pattern * repeats + pattern[:tail], palette)
