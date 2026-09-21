"""Modal-span recognition against a Python frequency and index oracle."""

import random
from collections import Counter

import pytest
from tightarray._core import _byte_trim


def oracle(raw):
    if not raw:
        return 0, 0, 0
    counts = Counter(raw)
    default = min(counts, key=lambda value: (-counts[value], value))
    changed = [index for index, value in enumerate(raw) if value != default]
    return (default, changed[0], changed[-1] + 1) if changed else (default, 0, 0)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\0",
        b"\xff",
        b"\xff" * 65537,
        bytes(range(256)),
        bytes(reversed(range(256))),
        b"\xff\0",
        b"\x80" * 20 + b"\xff" * 21,
        b"\xff" * 100 + b"\0" + b"\xff" * 100,
        b"\xff" + b"\0" * 100 + b"\xff",
        b"\0" * 100 + b"\xff",
        b"\xff" + b"\0" * 100,
        b"\x02" * 4 + b"\x01" * 4 + b"\x03" * 4,
    ],
)
def test_adversarial_bounds_and_ties(raw):
    assert _byte_trim(raw) == oracle(raw)


@pytest.mark.parametrize(
    "length", [0, 1, 2, 63, 64, 65, 255, 256, 257, 4096, 65535, 65536, 65537]
)
def test_random_oracle(length):
    rng = random.Random(length + 227)
    raw = bytes(rng.randrange(256) for _ in range(length))
    assert _byte_trim(raw) == oracle(raw)
    if length:
        default = rng.randrange(256)
        data = bytearray([default]) * length
        for _ in range(min(100, length)):
            data[rng.randrange(length)] = rng.randrange(256)
        assert _byte_trim(bytes(data)) == oracle(data)


def test_generated_trimmed_spans():
    rng = random.Random(20260922)
    for _ in range(200):
        default = rng.randrange(256)
        prefix = rng.randrange(200)
        suffix = rng.randrange(200)
        middle = bytes(rng.randrange(256) for _ in range(rng.randrange(200)))
        raw = bytes([default]) * prefix + middle + bytes([default]) * suffix
        result = _byte_trim(raw)
        assert result == oracle(raw)
        value, first, last = result
        restored = (
            bytes([value]) * first
            + raw[first:last]
            + bytes([value]) * (len(raw) - last)
        )
        assert restored == raw


@pytest.mark.parametrize("raw", [None, "abc", [1], bytearray(b"a"), memoryview(b"a")])
def test_strict_bytes(raw):
    with pytest.raises(TypeError):
        _byte_trim(raw)
