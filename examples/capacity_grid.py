"""Row-streamed totalistic CA: O(width) dense scratch, no dense whole grid.

State planes are lists of independent packed rows or uint8 ndarray rows.
Budget is observed process peak RSS, cooperatively checked (not an OS cap).
"""

import hashlib
import resource
import sys

import numpy as np
from numba import njit

from tightarray import Array


def peak_bytes():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024


def check_budget(budget):
    if budget is not None and peak_bytes() > budget:
        raise MemoryError("process peak RSS exceeded trial budget")


@njit
def update_row(north, center, south, output, states):
    size = len(center)
    for x in range(size):
        west = x - 1 if x else size - 1
        east = x + 1 if x + 1 < size else 0
        output[x] = (
            int(north[west])
            + int(north[x])
            + int(north[east])
            + int(center[west])
            + int(center[x])
            + int(center[east])
            + int(south[west])
            + int(south[x])
            + int(south[east])
        ) % states


class CapacityGrid:
    def __init__(self, rows, cols, states, backend, seed=123, budget=None):
        if (
            rows < 1
            or cols < 1
            or states not in (8, 32)
            or backend not in ("dense", "packed")
        ):
            raise ValueError("invalid grid parameters")
        self.rows, self.cols, self.states = rows, cols, states
        self.bits = (states - 1).bit_length()
        self.backend, self.budget = backend, budget
        self.source, self.target = [], []
        rng = np.random.default_rng(seed)
        for y in range(rows):
            row = rng.integers(0, states, cols, dtype=np.uint8)
            self.source.append(self.encode(row))
            # Touch all target pages, don't credit demand-zero uncommitted pages.
            self.target.append(self.encode(row))
            if y % 128 == 0:
                check_budget(budget)
        check_budget(budget)

    def encode(self, row):
        return row.copy() if self.backend == "dense" else Array(row, bits=self.bits)

    def decode(self, row):
        return (
            row
            if self.backend == "dense"
            else np.frombuffer(row.tobytes(), dtype=np.uint8)
        )

    @property
    def payload_bytes(self):
        return sum(row.nbytes for plane in (self.source, self.target) for row in plane)

    def step(self):
        north, center = self.decode(self.source[-1]), self.decode(self.source[0])
        output = np.empty(self.cols, dtype=np.uint8)
        for y in range(self.rows):
            south = self.decode(self.source[(y + 1) % self.rows])
            update_row(north, center, south, output, self.states)
            if self.backend == "dense":
                self.target[y][:] = output
            else:
                self.target[y] = self.encode(output)
            north, center = center, south
            if y % 128 == 0:
                check_budget(self.budget)
        self.source, self.target = self.target, self.source
        check_budget(self.budget)

    def digest(self):
        digest = hashlib.sha256()
        total = 0
        for row in self.source:
            decoded = self.decode(row)
            digest.update(decoded)
            total += int(decoded.sum(dtype=np.uint64))
        check_budget(self.budget)
        return {"sha256": digest.hexdigest(), "sum": total}
