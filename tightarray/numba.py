"""Optional zero-copy fixed-width packed access for Numba nopython kernels.

Explicitly import this module; importing tightarray never imports Numba. This is
an experimental descriptor API, not automatic @njit support for Array objects.
"""

import operator
from functools import lru_cache
from typing import NamedTuple

import numpy as np
from numba import njit

from . import Array


class NativeArray(NamedTuple):
    words: np.ndarray[tuple[int, ...], np.dtype[np.uint64]]
    start: int
    length: int
    bits: int
    aligned: bool


def as_native(array: Array) -> NativeArray:
    """Borrow physical words without unpacking; the ndarray retains the owner.

    Only fixed-width Array is accepted (not auto-widening Array API wrappers).
    A contiguous slice retains its original offset and root owner. Do not mutate
    the descriptor fields or its raw words. Use load/store for bounds and width
    checks. No concurrent writes: different elements can share a physical word.
    """
    if not isinstance(array, Array):
        raise TypeError("as_native requires a fixed-width tightarray.Array")
    buffer, start = array._word_view()
    return NativeArray(
        np.frombuffer(buffer, dtype=np.uint64),
        start,
        len(array),
        array.bits,
        array.layout == "word-aligned",
    )


@njit(inline="always")
def _load(array: NativeArray, index: int, bits: int, aligned: bool) -> int:
    """Load a logical value, including Python-style negative indices."""
    if index < 0:
        index += array.length
    if index < 0 or index >= array.length:
        raise IndexError("packed index out of range")
    position = array.start + index
    if aligned:
        lanes = 64 // bits
        word = position // lanes
        shift = (position % lanes) * bits
    else:
        position *= bits
        word = position // 64
        shift = position % 64
    value = array.words[word] >> np.uint64(shift)
    if not aligned and shift + bits > 64:
        value |= array.words[word + 1] << np.uint64(64 - shift)
    return np.int64(value & ((np.uint64(1) << np.uint64(bits)) - np.uint64(1)))


@njit(inline="always")
def _store(
    array: NativeArray, index: int, value: int, bits: int, aligned: bool
) -> None:
    """Reject overflow before touching either word; no implicit widening.

    Exceptions do not roll back writes made by earlier iterations of a caller's
    loop. Packed writes are not atomic and are not safe in a parallel prange loop.
    """
    if index < 0:
        index += array.length
    if index < 0 or index >= array.length:
        raise IndexError("packed index out of range")
    if isinstance(value, (float, np.float32, np.float64)):
        raise TypeError("packed values must be integers")
    if value < 0 or value >= (1 << bits):
        raise ValueError("value outside bit width")
    position = array.start + index
    if aligned:
        lanes = 64 // bits
        word = position // lanes
        shift = (position % lanes) * bits
    else:
        position *= bits
        word = position // 64
        shift = position % 64
    mask = (np.uint64(1) << np.uint64(bits)) - np.uint64(1)
    shifted_mask = mask << np.uint64(shift)
    array.words[word] = (array.words[word] & ~shifted_mask) | (
        np.uint64(value) << np.uint64(shift)
    )
    if not aligned and shift + bits > 64:
        spill = shift + bits - 64
        spill_mask = (np.uint64(1) << np.uint64(spill)) - np.uint64(1)
        array.words[word + 1] = (array.words[word + 1] & ~spill_mask) | (
            np.uint64(value) >> np.uint64(64 - shift)
        )


@njit(inline="always")
def load(array: NativeArray, index: int) -> int:
    return _load(array, index, array.bits, array.aligned)


@njit(inline="always")
def store(array: NativeArray, index: int, value: int) -> None:
    _store(array, index, value, array.bits, array.aligned)


@lru_cache(maxsize=16)
def specialize(bits: int, layout: str = "packed"):
    """Return checked read/write JIT helpers specialized for one width/layout.

    Capture the two helpers outside your @njit function. Unlike implicit dispatch
    on runtime tuple contents, each cached closure has its own compiled identity.
    """
    bits = operator.index(bits)
    if not 1 <= bits <= 8 or layout not in ("packed", "word-aligned"):
        raise ValueError("invalid bit width or layout")
    aligned = layout == "word-aligned"

    @njit(inline="always")
    def read(array, index):
        if array.bits != bits or array.aligned != aligned:
            raise ValueError("packed descriptor does not match specialization")
        return _load(array, index, bits, aligned)

    @njit(inline="always")
    def write(array, index, value):
        if array.bits != bits or array.aligned != aligned:
            raise ValueError("packed descriptor does not match specialization")
        _store(array, index, value, bits, aligned)

    return read, write
