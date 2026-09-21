"""Compare allocation-free selection against exhaustively materialized candidates."""

import random

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
            assert result.storage_info().stored_bytes == min(sizes)
