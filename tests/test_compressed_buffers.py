"""Byte-buffer ingestion must preserve logical indexing and value validation."""

from array import array

import pytest

from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("source", [bytearray(range(31)), array("B", range(31))])
def test_byte_buffer_is_copied_across_partial_chunks(source):
    result = CompressedArray(source, chunk_size=7)
    source[0] = 255
    assert result.tobytes() == bytes(range(31))
    result.write(4, memoryview(source)[2:9])
    source[2] = 254
    expected = bytearray(range(31))
    expected[4:11] = bytes(range(2, 9))
    assert result.tobytes() == expected


def test_strided_byte_buffer_uses_logical_elements():
    source = memoryview(bytes(range(31)))[::-2]
    result = CompressedArray(source, chunk_size=4)
    assert result.tobytes() == bytes(range(31))[::-2]
    result.write(0, source[::2])
    assert result[:8] == source[::2].tobytes()


def test_nonbyte_buffer_is_validated_as_elements_not_reinterpreted():
    source = array("H", [1, 255, 9])
    result = CompressedArray(source, chunk_size=2)
    assert result.tobytes() == bytes([1, 255, 9])
    for invalid in (array("b", [2, -1]), array("H", [3, 256])):
        with pytest.raises(ValueError):
            CompressedArray(invalid)
        with pytest.raises(ValueError):
            result.write(0, invalid)
        assert result.tobytes() == bytes([1, 255, 9])
