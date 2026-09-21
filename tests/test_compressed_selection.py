"""Compare allocation-free selection against exhaustively materialized candidates."""

import random
from itertools import groupby

import pytest

from tightarray import Array
from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("palette", [False, True])
def test_selection_matches_exhaustive_storage(palette):
    rng = random.Random(927)
    alphabets = [list(range(1 << bits)) for bits in range(1, 9)]
    alphabets += [[128, 255], [0, 64, 129, 255], list(range(128, 159))]
    for alphabet in alphabets:
        for length in [2, 7, 8, 9, 15, 16, 17, 63, 64, 65, 511, 4097]:
            raw = bytes(rng.choice(alphabet) for _ in range(length))
            colors = bytes(sorted(set(raw)))
            result = CompressedArray(raw, chunk_size=length, palette=palette)
            assert result.tobytes() == raw
            if len(colors) == 1:
                assert result.storage_info().stored_bytes == 0
                continue
            direct = Array(raw, bits=max(raw).bit_length())
            sizes = [direct.nbytes, len(raw)]
            if palette and len(colors) < 256:
                indices = Array(
                    [colors.index(value) for value in raw],
                    bits=(len(colors) - 1).bit_length(),
                )
                sizes.append(indices.nbytes + len(colors))
            run_size = sum(
                1 + max(1, ((len(list(group)) - 1).bit_length() + 6) // 7)
                for _, group in groupby(raw)
            )
            if palette and (len(colors) - 1).bit_length() < direct.bits:
                run_size += len(colors)
            sizes.append(run_size)
            for period in range(1, min(256, len(raw) // 2) + 1):
                if raw[period:] == raw[:-period]:
                    pattern = raw[:period]
                    bits = direct.bits
                    extra = 0
                    if palette and (len(colors) - 1).bit_length() < bits:
                        bits = (len(colors) - 1).bit_length()
                        extra = len(colors)
                        pattern = bytes(colors.index(value) for value in pattern)
                    sizes.append(Array(pattern, bits=bits).nbytes + extra + 1)
                    break
            for default in range(256):
                first = next(
                    (i for i, value in enumerate(raw) if value != default), len(raw)
                )
                last = next(
                    (i + 1 for i in range(len(raw) - 1, -1, -1) if raw[i] != default), 0
                )
                if first >= last or (first == 0 and last == len(raw)):
                    continue
                span = raw[first:last]
                span_colors = sorted(set(span))
                span_size = Array(span, bits=max(1, max(span).bit_length())).nbytes
                if palette and len(span_colors) < 256:
                    span_size = min(
                        span_size,
                        len(span_colors)
                        + Array(
                            [span_colors.index(value) for value in span],
                            bits=max(1, (len(span_colors) - 1).bit_length()),
                        ).nbytes,
                    )
                sizes.append(
                    span_size + 6
                )  # stored_bytes excludes common 2-byte header.
            assert result.storage_info().stored_bytes == min(sizes)
