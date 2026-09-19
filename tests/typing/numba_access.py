"""The optional Numba bridge must not leak dynamic types to consumers."""

from tightarray import Array
from tightarray.numba import NativeArray, as_native, load, specialize, store


def update(array: Array) -> int:
    native: NativeArray = as_native(array)
    read, write = specialize(array.bits, array.layout)
    write(native, 0, 1)
    store(native, 0, 0)
    return load(native, 0) + read(native, 0) + native.words.size
