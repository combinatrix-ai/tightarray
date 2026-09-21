"""Explicitly run after disposable native build; not required by main suite."""

import gc
import random
from concurrent.futures import ThreadPoolExecutor

import pytest

blosc2 = pytest.importorskip("blosc2")
CompressionContext = pytest.importorskip("ta_ccontext").CompressionContext


@pytest.mark.parametrize("codec", ["lz4", "zstd"])
@pytest.mark.parametrize("shuffle", [False, True])
@pytest.mark.parametrize("length", [0, 1, 7, 31, 64, 255, 4093, 4096, 16385])
def test_bytes_equal_public_compress2(codec, shuffle, length):
    rng = random.Random(length)
    context = CompressionContext(codec, length, shuffle)
    held = []
    for alphabet in (1, 8, 256, 32):
        raw = bytes(rng.randrange(alphabet) for _ in range(length))
        result = context.compress(raw)
        expected = blosc2.compress2(
            raw,
            codec=getattr(blosc2.Codec, codec.upper()),
            clevel=5,
            typesize=1,
            nthreads=1,
            filters=[blosc2.Filter.BITSHUFFLE if shuffle else blosc2.Filter.NOFILTER],
        )
        assert result == expected
        assert blosc2.decompress2(result, nthreads=1) == raw
        held.append((result, expected))
    context.close()
    context.close()
    del context
    gc.collect()
    assert all(result == expected for result, expected in held)


def test_validation_close_and_gil_serialization():
    for args, error in [
        (("bad", 10, False), ValueError),
        (("lz4", -1, False), ValueError),
        (("lz4", 1.5, False), TypeError),
        (("lz4", 10, 1), TypeError),
        (("lz4", 1 << 80, False), OverflowError),
    ]:
        with pytest.raises(error):
            CompressionContext(*args)
    context = CompressionContext("lz4", 8, False)
    for raw, error in [
        (b"x", ValueError),
        (bytearray(8), TypeError),
        (None, TypeError),
    ]:
        with pytest.raises(error):
            context.compress(raw)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(context.compress, [bytes([i]) * 8 for i in range(32)]))
    assert [blosc2.decompress2(value) for value in values] == [
        bytes([i]) * 8 for i in range(32)
    ]
    context.close()
    with pytest.raises(RuntimeError, match="closed"):
        context.compress(bytes(8))
