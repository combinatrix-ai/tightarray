"""Run encoding must survive cache admission, palette changes and cold reloads."""

import pytest

from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
@pytest.mark.parametrize("budget", [0, 32, 65536])
def test_runs_palette_mutation_eviction_and_partial_chunks(codec, budget):
    if codec != "none":
        pytest.importorskip("blosc2")
    expected = bytearray(bytes([200]) * 128 + bytes([250]) * 128)
    expected *= 5
    expected += b"xyz"
    array = CompressedArray(expected, chunk_size=256, cache_bytes=budget, codec=codec)
    assert array.storage_info().rle_chunks == 5
    assert array.storage_info().palette_chunks >= 5
    assert array.tobytes() == expected
    for index, value in [(3, 0), (255, 31), (300, 255), (1001, 199)]:
        array[index] = value
        expected[index] = value
    array.write(250, bytes(range(32)))
    expected[250:282] = bytes(range(32))
    assert array.tobytes() == expected
    array.clear_cache()
    assert array.tobytes() == expected
    assert array.storage_info().cache_bytes <= budget
    assert array[120:420:7] == expected[120:420:7]


def test_run_size_and_palette_disabled():
    raw = bytes([200]) * 128 + bytes([250]) * 128
    with_palette = CompressedArray(raw, chunk_size=256)
    without_palette = CompressedArray(raw, chunk_size=256, palette=False)
    assert with_palette.storage_info().stored_bytes == 6
    assert without_palette.storage_info().stored_bytes == 4
    assert with_palette.storage_info().rle_chunks == 1
    assert without_palette.storage_info().rle_chunks == 1
    assert without_palette.storage_info().palette_chunks == 0
    assert without_palette.tobytes() == raw
