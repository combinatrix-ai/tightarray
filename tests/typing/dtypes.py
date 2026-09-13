from typing import Any
from typing_extensions import assert_type
import numpy as np
from tightarray import array_api as xp

x = xp.asarray([0, 1, 7], dtype=xp.uint8)
assert_type(x, xp.Array[xp.uint8])
assert_type(x.dtype, np.dtype[np.uint8])
assert_type(x.storage_bits, int)
assert_type(x[0], xp.Array[np.uint8])
assert_type(x[::-1], xp.Array[np.uint8])
assert_type(next(iter(x)), xp.Array[np.uint8])
assert_type(xp.reshape(x, (1, 3)).T, xp.Array[np.uint8])
assert_type(xp.permute_dims(x, (0,)), xp.Array[np.uint8])
assert_type(xp.asarray(x), xp.Array[np.uint8])
assert_type(xp.asarray(np.array([1], dtype=np.float32)), xp.Array[np.float32])
assert_type(xp.asarray([1], dtype=np.dtype('uint8')), xp.Array[np.uint8])
assert_type(xp.asarray([1], dtype=np.dtype(np.uint8)), xp.Array[np.uint8])
assert_type(xp.astype(x, xp.float32), xp.Array[xp.float32])
assert_type(xp.astype(x, np.dtype(np.int16)), xp.Array[np.int16])
assert_type(x > 1, xp.Array[xp.bool])
assert_type(x == 1, xp.Array[np.bool_])
assert_type(xp.isnan(x), xp.Array[np.bool_])
assert_type(xp.all(x), xp.Array[np.bool_])
assert_type(xp.zeros_like(x), xp.Array[np.uint8])
assert_type(xp.zeros_like(x, dtype=xp.float32), xp.Array[np.float32])
assert_type(xp.full((2,), 1, dtype=xp.uint16), xp.Array[np.uint16])
assert_type(xp.arange(3, dtype=xp.int32), xp.Array[np.int32])
assert_type(xp.sum(x, dtype=xp.uint64), xp.Array[np.uint64])
assert_type(xp.sum(x), xp.Array[Any])
assert_type(x + 1, xp.Array[Any])  # Promotion inference is deliberately deferred.
assert_type(x.__array__(), np.ndarray[tuple[Any, ...], np.dtype[np.uint8]])
x[0] = 31
assert_type(x, xp.Array[np.uint8])
unknown: xp.Array = x
assert_type(unknown, xp.Array[Any])

def expects_uint8(value: xp.Array[np.uint8]) -> None:
    pass

def expects_unsigned(value: xp.Array[np.generic]) -> None:
    pass

expects_uint8(xp.astype(x, xp.float32))  # type: ignore[arg-type]
y: xp.Array[np.uint16] = x  # type: ignore[assignment]
expects_unsigned(x)  # type: ignore[arg-type]
bad: xp.Array[int]  # type: ignore[type-var]

# Every public scalar dtype participates in explicit construction and casts.
assert_type(xp.asarray([0, 1], dtype=xp.bool), xp.Array[xp.bool])
assert_type(xp.astype(x, xp.bool), xp.Array[xp.bool])
assert_type(xp.asarray([0, 1], dtype=xp.uint8), xp.Array[xp.uint8])
assert_type(xp.astype(x, xp.uint8), xp.Array[xp.uint8])
assert_type(xp.asarray([0, 1], dtype=xp.uint16), xp.Array[xp.uint16])
assert_type(xp.astype(x, xp.uint16), xp.Array[xp.uint16])
assert_type(xp.asarray([0, 1], dtype=xp.uint32), xp.Array[xp.uint32])
assert_type(xp.astype(x, xp.uint32), xp.Array[xp.uint32])
assert_type(xp.asarray([0, 1], dtype=xp.uint64), xp.Array[xp.uint64])
assert_type(xp.astype(x, xp.uint64), xp.Array[xp.uint64])
assert_type(xp.asarray([0, 1], dtype=xp.int8), xp.Array[xp.int8])
assert_type(xp.astype(x, xp.int8), xp.Array[xp.int8])
assert_type(xp.asarray([0, 1], dtype=xp.int16), xp.Array[xp.int16])
assert_type(xp.astype(x, xp.int16), xp.Array[xp.int16])
assert_type(xp.asarray([0, 1], dtype=xp.int32), xp.Array[xp.int32])
assert_type(xp.astype(x, xp.int32), xp.Array[xp.int32])
assert_type(xp.asarray([0, 1], dtype=xp.int64), xp.Array[xp.int64])
assert_type(xp.astype(x, xp.int64), xp.Array[xp.int64])
assert_type(xp.asarray([0, 1], dtype=xp.float32), xp.Array[xp.float32])
assert_type(xp.astype(x, xp.float32), xp.Array[xp.float32])
assert_type(xp.asarray([0, 1], dtype=xp.float64), xp.Array[xp.float64])
assert_type(xp.astype(x, xp.float64), xp.Array[xp.float64])
assert_type(xp.asarray([0, 1], dtype=xp.complex64), xp.Array[xp.complex64])
assert_type(xp.astype(x, xp.complex64), xp.Array[xp.complex64])
assert_type(xp.asarray([0, 1], dtype=xp.complex128), xp.Array[xp.complex128])
assert_type(xp.astype(x, xp.complex128), xp.Array[xp.complex128])
