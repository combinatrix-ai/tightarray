"""Exact period detection against a brute-force definition, including late noise."""

import random

import pytest
from tightarray._core import _byte_period


def reference(raw):
    for period in range(1, min(256, len(raw) // 2) + 1):
        if raw[period:] == raw[:-period]:
            return period
    return 0


@pytest.mark.parametrize("period", [1, 2, 31, 67, 128, 255, 256, 257])
def test_period_lengths_and_partial_tail(period):
    # A unique marker forces the intended minimal period even at p257.
    motif = b"\xff" + bytes((i % 127) for i in range(period - 1))
    for length in (period, 2 * period - 1, 2 * period, 2 * period + 1, 4096, 8193):
        raw = (motif * ((length + period - 1) // period))[:length]
        assert _byte_period(raw) == reference(raw)
        if length >= 2 * period:
            assert _byte_period(raw) == (period if period <= 256 else 0)
        if length > 512:
            changed = bytearray(raw)
            changed[-1] ^= 128
            assert _byte_period(bytes(changed)) == reference(bytes(changed)) == 0


def test_empty_single_and_no_period():
    for raw in (
        b"",
        b"a",
        b"ab",
        bytes(range(256)),
        bytes(range(256)) * 2,
        b"abcab",
        b"abcabcab",
    ):
        assert _byte_period(raw) == reference(raw)


def test_randomized_against_bruteforce():
    rng = random.Random(21922)
    for _ in range(600):
        period = rng.randrange(1, 301)
        alphabet = rng.choice((2, 3, 16, 256))
        motif = bytes(rng.randrange(alphabet) for _ in range(period))
        length = rng.randrange(0, 2200)
        raw = (motif * ((length + period - 1) // period))[:length]
        if raw and rng.randrange(2):
            changed = bytearray(raw)
            changed[rng.randrange(len(raw))] ^= 128
            raw = bytes(changed)
        assert _byte_period(raw) == reference(raw)


def test_exhaustive_short_binary_strings():
    for length in range(11):
        for value in range(1 << length):
            raw = bytes((value >> i) & 1 for i in range(length))
            assert _byte_period(raw) == reference(raw)


@pytest.mark.parametrize(
    "raw", [None, "abc", [1, 2], bytearray(b"aa"), memoryview(b"aa")]
)
def test_strict_bytes(raw):
    with pytest.raises(TypeError):
        _byte_period(raw)
