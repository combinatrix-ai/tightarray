"""Periodic 2D cyclic cellular automaton: a worked fixed-width Numba example.

A cell advances to (state+1) % states iff one of its four von Neumann neighbors
has that state. All cells read the previous generation (synchronous update).
The grid is intentionally an application example, not part of tightarray's API.
"""

import operator
from functools import lru_cache
from typing import Literal, cast

import numpy as np
from numba import njit
from numpy.typing import NDArray

from tightarray import Array
from tightarray.numba import NativeArray, as_native, specialize


@lru_cache(maxsize=16)
def _packed_kernel(bits, aligned):
    read, write = specialize(bits, "word-aligned" if aligned else "packed")

    @njit
    def kernel(source, target, rows, cols, states, steps):
        for _ in range(steps):
            for y in range(rows):
                north = (y - 1 if y else rows - 1) * cols
                south = (y + 1 if y + 1 < rows else 0) * cols
                row = y * cols
                for x in range(cols):
                    i = row + x
                    current = read(source, i)
                    following = current + 1
                    if following == states:
                        following = 0
                    west = row + (x - 1 if x else cols - 1)
                    east = row + (x + 1 if x + 1 < cols else 0)
                    advance = (
                        read(source, north + x) == following
                        or read(source, south + x) == following
                        or read(source, west) == following
                        or read(source, east) == following
                    )
                    write(target, i, following if advance else current)
            source, target = target, source

    return kernel


def evolve_packed_into(source, target, rows, cols, states, steps):
    _packed_kernel(source.bits, source.aligned)(
        source, target, rows, cols, states, steps
    )


@njit
def evolve_dense_into(source, target, rows, cols, states, steps):
    for _ in range(steps):
        for y in range(rows):
            north = (y - 1 if y else rows - 1) * cols
            south = (y + 1 if y + 1 < rows else 0) * cols
            row = y * cols
            for x in range(cols):
                i = row + x
                current = int(source[i])
                following = current + 1
                if following == states:
                    following = 0
                west = row + (x - 1 if x else cols - 1)
                east = row + (x + 1 if x + 1 < cols else 0)
                advance = (
                    source[north + x] == following
                    or source[south + x] == following
                    or source[west] == following
                    or source[east] == following
                )
                target[i] = following if advance else current
        source, target = target, source


def evolve_numpy_into(
    source: NDArray[np.uint8], target: NDArray[np.uint8], states: int, steps: int
) -> None:
    following = np.empty_like(source)
    for _ in range(steps):
        np.add(source, 1, out=following)
        following[following == states] = 0
        advance = (
            (np.roll(source, 1, axis=0) == following)
            | (np.roll(source, -1, axis=0) == following)
            | (np.roll(source, 1, axis=1) == following)
            | (np.roll(source, -1, axis=1) == following)
        )
        np.copyto(target, source)
        np.copyto(target, following, where=advance)
        source, target = target, source


class PackedGrid:
    """Fixed-size, double-buffered grid. step() mutates this simulation only."""

    def __init__(
        self,
        values: NDArray[np.uint8],
        *,
        states: int,
        layout: Literal["packed", "word-aligned"] = "packed",
    ) -> None:
        states = operator.index(states)
        values = np.asarray(values)
        if not 2 <= states <= 256:
            raise ValueError("states must be 2..256")
        if values.ndim != 2 or min(values.shape) < 1 or values.dtype.kind not in "iu":
            raise ValueError("expected a nonempty 2D integer grid")
        if np.any(values < 0) or np.any(values >= states):
            raise ValueError("state outside alphabet")
        self.rows, self.cols = values.shape
        self.states = states
        bits = cast(Literal[1, 2, 3, 4, 5, 6, 7, 8], (states - 1).bit_length())
        self._source = Array(values.astype(np.uint8).ravel(), bits=bits, layout=layout)
        self._target = Array(
            np.zeros(values.size, dtype=np.uint8), bits=bits, layout=layout
        )
        self._source_native: NativeArray = as_native(self._source)
        self._target_native: NativeArray = as_native(self._target)

    @property
    def nbytes(self) -> int:
        """Two packed backing allocations; Python/JIT metadata excluded."""
        return self._source.nbytes + self._target.nbytes

    def step(self, steps: int = 1) -> None:
        steps = operator.index(steps)
        if steps < 0:
            raise ValueError("steps must be nonnegative")
        evolve_packed_into(
            self._source_native,
            self._target_native,
            self.rows,
            self.cols,
            self.states,
            steps,
        )
        if steps % 2:
            self._source, self._target = self._target, self._source
            self._source_native, self._target_native = (
                self._target_native,
                self._source_native,
            )

    def to_numpy(self) -> NDArray[np.uint8]:
        """Materialize logical uint8 values explicitly, e.g. for visualization."""
        return np.frombuffer(self._source.tobytes(), dtype=np.uint8).reshape(
            self.rows, self.cols
        )
