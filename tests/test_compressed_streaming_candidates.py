import random

import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_streaming_candidates import (
    BASELINE,
    cases,
    pinned_baseline,
    streaming_class,
    timed,
    trace,
    traced_encode,
)


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
def test_exact_records_and_codec_traces(codec):
    with pinned_baseline(BASELINE) as (base, source):
        new = streaming_class(base, source)
        for raw in cases(4096).values():
            assert traced_encode(base, raw, codec) == traced_encode(new, raw, codec)
            writes, expected = trace(raw)
            old = timed(base, raw, codec, writes, expected, 1)[1]
            assert old == timed(new, raw, codec, writes, expected, 1)[1]


@pytest.mark.parametrize(
    "sizes", [(16,), (32,), (64,), (128,), (352,), (16, 8, 4), (400, 32, 24)]
)
def test_compressed_ties_and_pruning_order(sizes):
    rng = random.Random(8244)
    with pinned_baseline(BASELINE) as (base, source):
        new = streaming_class(base, source)
        # 512 high labels give uncompressed palette cost352: compressed direct
        # ties must lose to that uncompressed candidate despite compression order.
        for length in (63, 64, 65, 127, 128, 129, 512, 4096):
            for low, states in ((0, 8), (224, 32), (128, 128)):
                raw = bytes(rng.randrange(low, low + states) for _ in range(length))
                assert traced_encode(base, raw, "zstd", sizes) == traced_encode(
                    new, raw, "zstd", sizes
                )


def test_structured_ties():
    rng = random.Random(8245)
    with pinned_baseline(BASELINE) as (base, source):
        new = streaming_class(base, source)
        inputs = [
            bytes(range(32)) * 128,
            b"\0" * 256 + bytes(rng.randrange(32) for _ in range(512)) + b"\0" * 256,
        ]
        for raw in inputs:
            plain = base((), codec="none")._encode(raw)
            for size in (len(plain) - 3, len(plain) - 2, len(plain) - 1):
                assert traced_encode(base, raw, "zstd", (size,)) == traced_encode(
                    new, raw, "zstd", (size,)
                )


@pytest.mark.parametrize("codec", ["lz4", "zstd"])
def test_mutated_flush_compression_trace(codec):
    with pinned_baseline(BASELINE) as (base, source):
        new = streaming_class(base, source)
        for raw in cases(4096).values():
            writes, expected = trace(raw)
            results = []
            for cls in (base, new):
                calls = []

                class Traced(cls):
                    trace_calls = calls

                    def _compress(self, payload, *, shuffle):
                        self.trace_calls.append((payload, shuffle))
                        return super()._compress(payload, shuffle=shuffle)

                array = Traced(raw, codec=codec)
                calls.clear()
                for start, values in writes:
                    array.write(start, values)
                array.flush()
                assert array.tobytes() == expected
                results.append((tuple(array._chunks), calls))
            assert results[0] == results[1]
