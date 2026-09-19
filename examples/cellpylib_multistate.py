"""Experimental multi-state periodic CA paths, with explicit history policy.

The totalistic callback calls CellPyLib itself; other callbacks are custom rules
run through its real evolve2d API. The final-only mode is NOT API-compatible.
"""

from functools import cache

import cellpylib as cpl
import numpy as np
from numba import njit

from tightarray import Array
from tightarray.numba import as_native, specialize

RULES = ("totalistic", "cyclic", "transport")


def rule_callback(rule, states):
    if rule not in RULES or not 2 <= states <= 32:
        raise ValueError("unknown rule or unsupported state count")
    # Digit for neighborhood sum s is s % states (least significant first).
    number = sum((s % states) * states**s for s in range(9 * (states - 1) + 1))
    if rule == "totalistic":
        return lambda n, c, t: cpl.totalistic_rule(n, k=states, rule=number)
    if rule == "transport":
        return lambda n, c, t: n[1, 0]

    def cyclic(n, c, t):
        following = (int(n[1, 1]) + 1) % states
        return (
            following
            if any(n[y, x] == following for y, x in ((0, 1), (2, 1), (1, 0), (1, 2)))
            else n[1, 1]
        )

    return cyclic


@njit(inline="always")
def _dense_read(a, i):
    return a[i]


@njit(inline="always")
def _dense_write(a, i, v):
    a[i] = v


@cache
def kernel(rule, bits, backend):
    read, write = (
        (_dense_read, _dense_write) if backend == "dense" else specialize(bits, backend)
    )

    @njit
    def evolve(source, target, rows, cols, states, steps, history):
        for t in range(steps):
            for y in range(rows):
                north = (y - 1 if y else rows - 1) * cols
                south = (y + 1 if y + 1 < rows else 0) * cols
                row = y * cols
                for x in range(cols):
                    west = x - 1 if x else cols - 1
                    east = x + 1 if x + 1 < cols else 0
                    i = row + x
                    if rule == "transport":
                        value = read(source, row + west)
                    elif rule == "cyclic":
                        current = read(source, i)
                        following = (current + 1) % states
                        advance = (
                            read(source, north + x) == following
                            or read(source, south + x) == following
                            or read(source, row + west) == following
                            or read(source, row + east) == following
                        )
                        value = following if advance else current
                    else:
                        value = (
                            read(source, north + west)
                            + read(source, north + x)
                            + read(source, north + east)
                            + read(source, row + west)
                            + read(source, i)
                            + read(source, row + east)
                            + read(source, south + west)
                            + read(source, south + x)
                            + read(source, south + east)
                        ) % states
                    write(target, i, value)
                    if history.shape[0]:
                        history[t + 1, y, x] = value
            source, target = target, source

    return evolve


def simulate(initial, steps, states, rule, backend, *, full_history=False):
    """steps is number of updates, unlike CellPyLib's inclusive timesteps."""
    if rule not in RULES or backend not in ("numpy", "dense", "packed", "word-aligned"):
        raise ValueError("unknown rule/backend")
    if not 2 <= states <= 32 or steps < 0 or not isinstance(steps, int):
        raise ValueError("invalid state count or steps")
    a = np.asarray(initial)
    if a.ndim != 2 or min(a.shape) < 1 or a.dtype != np.uint8 or np.any(a >= states):
        raise ValueError("expected nonempty uint8 grid with in-range states")
    rows, cols = a.shape
    bits = (states - 1).bit_length()
    history = np.empty((steps + 1 if full_history else 0, rows, cols), dtype=np.uint8)
    if full_history:
        history[0] = a
    if backend == "numpy":
        source = a.copy()
        for t in range(steps):
            if rule == "transport":
                source = np.roll(source, 1, axis=1)
            elif rule == "totalistic":
                total = np.zeros_like(source, dtype=np.uint16)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        total += np.roll(source, (dy, dx), axis=(0, 1))
                source = (total % states).astype(np.uint8)
            else:
                following = (source + 1) % states
                advance = np.zeros_like(source, dtype=bool)
                for axis in (0, 1):
                    for shift in (-1, 1):
                        advance |= np.roll(source, shift, axis=axis) == following
                source = np.where(advance, following, source)
            if full_history:
                history[t + 1] = source
        return history if full_history else source
    if backend == "dense":
        source, target = a.ravel().copy(), np.empty(a.size, dtype=np.uint8)
        kernel(rule, bits, backend)(source, target, rows, cols, states, steps, history)
        result = target if steps % 2 else source
    else:
        source = Array(a.ravel(), bits=bits, layout=backend)
        target = Array(np.zeros(a.size, dtype=np.uint8), bits=bits, layout=backend)
        kernel(rule, bits, backend)(
            as_native(source), as_native(target), rows, cols, states, steps, history
        )
        if full_history:
            return history
        result = np.frombuffer(
            (target if steps % 2 else source).tobytes(), dtype=np.uint8
        )
    return history if full_history else result.reshape(a.shape)
