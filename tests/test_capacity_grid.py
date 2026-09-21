import numpy as np
import pytest

pytest.importorskip("numba")
from examples.capacity_grid import CapacityGrid, peak_bytes


@pytest.mark.parametrize("states", [8, 32])
@pytest.mark.parametrize("shape", [(1, 1), (2, 7), (11, 65)])
def test_streaming(states, shape):
    rows, cols = shape
    # Reproduce row-wise RNG generation exactly, including partial byte blocks.
    rng = np.random.default_rng(123)
    expected = np.stack(
        [rng.integers(0, states, cols, dtype=np.uint8) for _ in range(rows)]
    )
    grids = [CapacityGrid(rows, cols, states, b) for b in ("dense", "packed")]
    for _ in range(4):
        for grid in grids:
            np.testing.assert_array_equal(
                np.stack([grid.decode(r) for r in grid.source]), expected
            )
        assert grids[0].digest() == grids[1].digest()
        total = np.zeros(shape, dtype=np.uint16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                total += np.roll(expected, (dy, dx), axis=(0, 1))
        expected = (total % states).astype(np.uint8)
        for grid in grids:
            grid.step()


def test_budget():
    with pytest.raises(MemoryError):
        CapacityGrid(8, 8, 8, "packed", budget=1)
    assert peak_bytes() > 0


def test_cellpylib_totalistic():
    cpl = pytest.importorskip("cellpylib")
    from examples.cellpylib_multistate import rule_callback

    grid = CapacityGrid(9, 13, 32, "packed")
    initial = np.stack([grid.decode(row) for row in grid.source])
    expected = cpl.evolve2d(initial[None], 4, rule_callback("totalistic", 32))
    for t in range(1, 4):
        grid.step()
        np.testing.assert_array_equal(
            np.stack([grid.decode(row) for row in grid.source]), expected[t]
        )
