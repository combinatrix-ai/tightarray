import marshal
from pathlib import Path

import numpy as np
import pytest

from benchmarks.real_sokoban_search import SOURCE, encode, run_case


def test_keys_preserve_board_content():
    fixed = np.zeros((10, 10), dtype=np.int64)
    variants = []
    for position in (0, 7, 21, 63, 99):
        for value in range(1, 6):
            board = fixed.copy()
            board.flat[position] = value
            variants.append(board)
    for backend in ("marshal", "uint8", "tightarray", "sparse"):
        keys = [encode(board, backend, fixed) for board in variants]
        assert len(set(keys)) == len(variants)
        copies = [encode(board.copy(), backend, fixed) for board in variants]
        if backend == "marshal":
            # CPython may add FLAG_REF for retained objects but not temporaries.
            # Preserve the upstream baseline; marshal bytes are not canonical keys.
            expected = [board.tobytes() for board in variants]
            assert [marshal.loads(key) for key in keys] == expected
            assert [marshal.loads(key) for key in copies] == expected
        else:
            assert keys == copies


@pytest.mark.skipif(
    not Path(SOURCE).exists(), reason="Optional pinned upstream source not downloaded"
)
def test_real_search_unchanged():
    rows = [
        run_case(SOURCE, 11, backend, 100)
        for backend in ("marshal", "uint8", "tightarray", "sparse")
    ]
    assert all(row["identity"] == rows[0]["identity"] for row in rows)
    assert rows[0]["identity"]["visited"] > 0
