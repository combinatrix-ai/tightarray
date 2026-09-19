import numpy as np
import pytest

pytest.importorskip("numba")
from examples.lattice import PackedGrid, evolve_dense_into, evolve_numpy_into


def reference(values, states, steps):
    values = values.tolist()
    rows, cols = len(values), len(values[0])
    for _ in range(steps):
        result = [[0] * cols for _ in range(rows)]
        for y in range(rows):
            for x in range(cols):
                value = values[y][x]
                following = (value + 1) % states
                neighbors = [
                    values[(y - 1) % rows][x],
                    values[(y + 1) % rows][x],
                    values[y][(x - 1) % cols],
                    values[y][(x + 1) % cols],
                ]
                result[y][x] = following if following in neighbors else value
        values = result
    return np.array(values, dtype=np.uint8)


@pytest.mark.parametrize("shape", [(1, 1), (1, 7), (5, 1), (7, 13)])
@pytest.mark.parametrize("states", [2, 3, 4, 8, 32, 256])
def test_backends_match_independent_rule(shape, states):
    values = np.random.default_rng(17).integers(0, states, shape, dtype=np.uint8)
    for steps in [0, 1, 2, 5]:
        expected = reference(values, states, steps)
        for layout in ["packed", "word-aligned"]:
            grid = PackedGrid(values, states=states, layout=layout)
            grid.step(steps)
            np.testing.assert_array_equal(grid.to_numpy(), expected)
        a, b = values.copy(), np.empty_like(values)
        evolve_numpy_into(a, b, states, steps)
        np.testing.assert_array_equal(b if steps % 2 else a, expected)
        a, b = values.copy().ravel(), np.empty(values.size, dtype=np.uint8)
        evolve_dense_into(a, b, *shape, states, steps)
        np.testing.assert_array_equal((b if steps % 2 else a).reshape(shape), expected)


def test_repeated_steps_and_validation():
    values = np.array([[0, 1, 2], [2, 0, 1]], dtype=np.uint8)
    grid = PackedGrid(values, states=3)
    grid.step(2)
    grid.step(3)
    np.testing.assert_array_equal(grid.to_numpy(), reference(values, 3, 5))
    for states in [1, 257]:
        with pytest.raises(ValueError):
            PackedGrid(values, states=states)
    with pytest.raises(ValueError):
        PackedGrid(values, states=2)
    with pytest.raises(ValueError):
        PackedGrid(np.empty((0, 1), dtype=np.uint8), states=2)
    with pytest.raises(ValueError):
        grid.step(-1)
