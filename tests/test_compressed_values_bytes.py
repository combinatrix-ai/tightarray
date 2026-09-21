"""Benchmark-only input fast-path validation; no Git history needed."""

from array import array

import pytest

import tightarray.compressed as live
from benchmarks.compressed_values_bytes import INSERTION, MARKER, fast_values, inject


@pytest.mark.parametrize("raw", [b"", b"\x00", bytes(range(256))])
def test_exact_bytes_identity(raw):
    assert fast_values()(raw) is raw


def test_subclass_and_mutable_buffer_snapshot():
    class WeirdBytes(bytes):
        def __iter__(self):
            raise AssertionError("buffer path should precede iteration")

    fn = fast_values()
    for source in (
        WeirdBytes(b"abc"),
        bytearray(b"abc"),
        memoryview(bytearray(b"abc")),
    ):
        result = fn(source)
        assert type(result) is bytes
        assert result == live._values(source) == b"abc"
        if not isinstance(source, bytes):
            source[0] = 255
            assert result == b"abc"


@pytest.mark.parametrize(
    "source", [3, [256], [-1], [1.5], array("b", [-1]), array("H", [256])]
)
def test_invalid_inputs_match_baseline(source):
    with pytest.raises(Exception) as baseline:
        live._values(source)
    with pytest.raises(type(baseline.value)):
        fast_values()(source)


def test_logical_buffer_and_iterable_paths():
    for source in (memoryview(b"abcdef")[::2], array("H", [1, 255]), [0, 255], (1, 2)):
        assert fast_values()(source) == live._values(source)
    assert fast_values()(iter([1, 255])) == b"\x01\xff"


def test_injection_is_idempotent():
    original = "def _values(values):\n" + MARKER + "\n    return bytes(values)\n"
    once = inject(original)
    assert once.count(INSERTION) == 1
    assert inject(once) == once
