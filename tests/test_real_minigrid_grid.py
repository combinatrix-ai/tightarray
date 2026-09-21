from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("minigrid")
pytest.importorskip("blosc2")
from minigrid.core.grid import Grid
from minigrid.core.world_object import Box, Door, Key

from benchmarks.real_minigrid_grid import GridSnapshot, trace


@pytest.mark.parametrize("backend", ["numpy", "packed", "blosc-lz4", "blosc-zstd"])
def test_actual_trace_roundtrip(backend):
    for frame in trace("MiniGrid-DoorKey-8x8-v0", 10):
        snapshot = GridSnapshot(frame, backend)
        np.testing.assert_array_equal(snapshot.encoded(), frame)
        grid, mask = snapshot.decoded()
        np.testing.assert_array_equal(grid.encode(mask), frame)


def test_door_mutation_snapshot_is_not_live():
    grid = Grid(3, 3)
    door = Door("yellow", is_locked=True)
    grid.set(1, 1, door)
    before = GridSnapshot(grid.encode(), "packed")
    assert door.toggle(SimpleNamespace(carrying=Key("yellow")), (1, 1))
    assert grid.get(1, 1) is door
    after = GridSnapshot(grid.encode(), "packed")
    assert before.encoded()[1, 1, 2] == 2
    assert after.encoded()[1, 1, 2] == 0
    restored, _ = after.decoded()
    assert restored.get(1, 1) is not door
    assert restored.get(1, 1).is_open


def test_upstream_encoding_cannot_preserve_box_contents():
    grid = Grid(3, 3)
    grid.set(1, 1, Box("red", contains=Key("blue")))
    restored, _ = GridSnapshot(grid.encode(), "packed").decoded()
    assert grid.get(1, 1).contains is not None
    assert restored.get(1, 1).contains is None


def test_visibility_mask():
    grid = Grid(3, 3)
    grid.set(1, 1, Key("blue"))
    mask = np.ones((3, 3), dtype=bool)
    mask[1, 1] = False
    encoded = grid.encode(mask)
    restored, visible = GridSnapshot(encoded, "packed").decoded()
    np.testing.assert_array_equal(visible, mask)
    np.testing.assert_array_equal(restored.encode(visible), encoded)
