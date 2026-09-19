"""Experimental CellPyLib evolve2d adapter; only binary official Life is accelerated.

All other rules/options delegate to unmodified CellPyLib. Full dense history is
returned, including any supplied prefix. No monkey patch or global state change.
"""

import operator

import cellpylib as cpl
import numpy as np
from numba import njit

from tightarray import Array
from tightarray.numba import as_native, specialize

_read, _write = specialize(1, "packed")


@njit
def _dense(source, target, output, prefix):
    rows, cols = source.shape
    for t in range(prefix, len(output)):
        for y in range(rows):
            for x in range(cols):
                count = 0
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        count += source[(y + dy) % rows, (x + dx) % cols]
                alive = source[y, x]
                value = count == 3 or (alive == 1 and count == 4)
                target[y, x] = value
                output[t, y, x] = value
        source, target = target, source


@njit
def _packed(source, target, output, prefix):
    rows, cols = output.shape[1:]
    for t in range(prefix, len(output)):
        for y in range(rows):
            for x in range(cols):
                count = 0
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        count += _read(
                            source, ((y + dy) % rows) * cols + (x + dx) % cols
                        )
                alive = _read(source, y * cols + x)
                value = count == 3 or (alive == 1 and count == 4)
                _write(target, y * cols + x, value)
                output[t, y, x] = value
        source, target = target, source


def evolve2d(
    cellular_automaton,
    timesteps,
    apply_rule,
    r=1,
    neighbourhood="Moore",
    memoize=False,
    *,
    backend="packed",
):
    """Same output contract as CellPyLib; backend is packed or dense (ablation)."""
    if backend not in ("packed", "dense"):
        raise ValueError("backend must be packed or dense")
    a = cellular_automaton
    eligible = (
        apply_rule is cpl.game_of_life_rule
        and r == 1
        and neighbourhood == "Moore"
        and memoize in (False, True, "recursive")
        and isinstance(a, np.ndarray)
        and a.ndim == 3
        and min(a.shape) > 0
        and a.dtype.kind in "biu"
        and np.all((a == 0) | (a == 1))
        and isinstance(timesteps, (int, np.integer))
        and timesteps >= 1
    )
    if not eligible:
        return cpl.evolve2d(a, timesteps, apply_rule, r, neighbourhood, memoize)
    steps = operator.index(timesteps)
    output = np.empty((len(a) + steps - 1, *a.shape[1:]), dtype=a.dtype)
    output[: len(a)] = a
    if steps == 1:
        return output
    source = np.asarray(a[-1], dtype=np.uint8).copy()
    if backend == "dense":
        _dense(source, np.empty_like(source), output, len(a))
    else:
        packed = Array(source.ravel(), bits=1)
        target = Array(np.zeros(source.size, dtype=np.uint8), bits=1)
        _packed(as_native(packed), as_native(target), output, len(a))
    return output
