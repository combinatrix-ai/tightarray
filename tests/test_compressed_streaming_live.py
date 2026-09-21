"""Adopted encoder must match pinned exhaustive selection, including codec calls."""

import random

import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_streaming_candidates import (
    BASELINE,
    cases,
    pinned_baseline,
    timed,
    trace,
    traced_encode,
)
from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
def test_live_records_and_changed_writeback(codec):
    with pinned_baseline(BASELINE) as (base, _):
        for raw in cases(4096).values():
            assert traced_encode(base, raw, codec) == traced_encode(
                CompressedArray, raw, codec
            )
            writes, expected = trace(raw)
            assert (
                timed(base, raw, codec, writes, expected, 1)[1]
                == timed(CompressedArray, raw, codec, writes, expected, 1)[1]
            )


@pytest.mark.parametrize("palette", [False, True])
def test_live_boundaries_widths_and_ties(palette):
    rng = random.Random(8250)

    class Live(CompressedArray):
        def __init__(self, values=(), **kwargs):
            super().__init__(values, palette=palette, **kwargs)

    with pinned_baseline(BASELINE) as (base, _):

        class Old(base):
            def __init__(self, values=(), **kwargs):
                super().__init__(values, palette=palette, **kwargs)

        for bits in range(1, 9):
            for length in (1, 7, 63, 64, 65, 127, 129, 512):
                for high in (False, True):
                    low = 256 - (1 << bits) if high else 0
                    raw = bytes(
                        rng.randrange(low, low + (1 << bits)) for _ in range(length)
                    )
                    for sizes in ((16,), (32,), (64,), (352,), (400, 32, 24)):
                        assert traced_encode(Old, raw, "zstd", sizes) == traced_encode(
                            Live, raw, "zstd", sizes
                        )
        for raw in cases(4096).values():
            plain = Old((), codec="none")._encode(raw)
            if isinstance(plain, bytes):
                for size in (len(plain) - 3, len(plain) - 2, len(plain) - 1):
                    assert traced_encode(Old, raw, "zstd", (size,)) == traced_encode(
                        Live, raw, "zstd", (size,)
                    )
