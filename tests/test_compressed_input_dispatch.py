"""Dispatch prototype validates strict inputs without requiring Git history."""

from array import array
from pathlib import Path

import pytest

import tightarray.compressed as live
from benchmarks.compressed_input_dispatch import modules, sources
from benchmarks.compressed_values_bytes import INSERTION, MARKER


@pytest.fixture
def policies():
    helper = Path(live.__file__).read_text()
    original = helper.replace(INSERTION + MARKER, MARKER)
    helper = original.replace(MARKER, INSERTION + MARKER)
    with modules(sources(original, helper)) as result:
        yield result


@pytest.mark.parametrize(
    "invalid",
    [3, [-1], [256], [1.2], (-1,), (256,), array("b", [-1]), array("H", [256])],
)
def test_write_failure_preserves_all_chunks(policies, invalid):
    for policy in policies.values():
        arr = policy.CompressedArray(bytes(range(8)), chunk_size=4)
        with pytest.raises((TypeError, ValueError)):
            arr.write(0, invalid)
        assert arr.tobytes() == bytes(range(8))


def test_subclasses_and_snapshot(policies):
    class ListSubclass(list):
        def __iter__(self):
            return iter([7, 8])

    class TupleSubclass(tuple):
        def __iter__(self):
            return iter([9, 10])

    class BytesSubclass(bytes):
        def __iter__(self):
            raise AssertionError("buffer semantics must survive")

    for policy in policies.values():
        arr = policy.CompressedArray(bytes(8), chunk_size=4)
        arr.write(0, ListSubclass([1, 2]))
        arr.write(2, TupleSubclass([1, 2]))
        arr.write(4, BytesSubclass(b"ab"))
        mutable = bytearray(b"cd")
        arr.write(6, mutable)
        mutable[0] = 0
        assert arr.tobytes() == bytes([7, 8, 9, 10]) + b"abcd"


def test_generator_validation_before_mutation(policies):
    for policy in policies.values():
        arr = policy.CompressedArray(bytes(8), chunk_size=4)
        with pytest.raises(ValueError):
            arr.write(0, (value for value in [1, 2, 3, 4, 256]))
        assert arr.tobytes() == bytes(8)
        arr.write(0, memoryview(b"abcdef")[::2])
        assert arr[:3] == b"ace"
