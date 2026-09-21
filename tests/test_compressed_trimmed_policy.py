import numpy as np
import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_trimmed_policy import cases, pinned_baseline, trimmed_class


@pytest.mark.parametrize(
    "name",
    [
        "half-random-half-zero",
        "half-zero-half-random",
        "central-island",
        "random32",
        "half-with-edge-outlier",
        "rare-spikes",
        "uniform-chunks",
    ],
)
def test_trimmed_roundtrip_and_boundary_mutation(name):
    data = dict(cases(4096))[name].tobytes()
    with pinned_baseline() as (base, _):
        cls = trimmed_class(base)
        array = cls(data, chunk_size=4096, cache_bytes=4096)
        assert array.tobytes() == data
        assert array[::-13] == data[::-13]
        for index in (0, 1535, 1536, 2047, 2048, 2559, 2560, 4095):
            assert array[index] == data[index]
        expected = bytearray(data)
        for index in (0, 1536, 2048, 4095):
            array[index] = 255
            expected[index] = 255
        array.flush()
        array.clear_cache()
        assert array.tobytes() == bytes(expected)
        array.write(1520, bytes(range(64)))
        expected[1520:1584] = bytes(range(64))
        array.clear_cache()
        assert array.tobytes() == bytes(expected)


def test_trim_selected_and_partial_chunks_zero_cache():
    data = bytes(range(32)) * 32 + bytes(3072)
    with pinned_baseline() as (base, _):
        cls = trimmed_class(base)
        array = cls(data + bytes(31), chunk_size=4096, cache_bytes=0)
        assert array._chunks[0][0] == 0
        assert len(array._chunks[0]) < len(base(data)._chunks[0])
        assert array.read(1000, 4100) == (data + bytes(31))[1000:4100]
        array[-1] = 7
        assert array[-1] == 7
        array.flush()
        assert array.storage_info().cache_bytes == 0
        assert np.array_equal(
            np.frombuffer(array.tobytes(), dtype=np.uint8)[-31:], [0] * 30 + [7]
        )
