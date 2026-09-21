import numpy as np
import pytest

from benchmarks.real_sokoban_native_keys import native_key
from benchmarks.real_sokoban_search import encode


@pytest.mark.parametrize("shape", [(1, 1), (1, 7), (3, 7), (10, 10), (4, 17)])
def test_fused_keys_match_original_packed_word_bytes(shape):
    rng = np.random.default_rng(8411)
    board = rng.integers(6, size=shape, dtype=np.int64)
    for value in (board, board[:, ::-1], np.zeros(shape, dtype=np.int64)):
        assert native_key(value) == encode(value, "tightarray", np.zeros(shape))
        assert native_key(value.copy()) == native_key(value)
