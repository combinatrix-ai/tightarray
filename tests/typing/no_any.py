"""Run with disallow-any-expr: public results cannot silently disable checking."""
from typing_extensions import assert_type, TypeVar
import numpy as np
from tightarray import Array
from tightarray import array_api as xp

x = xp.asarray([0, 1, 7], dtype=xp.uint8)
unknown = xp.asarray([0, 1, 7])
assert_type(unknown, xp.Array[xp.Scalar])
assert_type(unknown.dtype, np.dtype[xp.Scalar])
assert_type(xp.sum(x), xp.Array[np.uint64])
assert_type(xp.sum(xp.asarray([True], dtype=xp.bool)), xp.Array[np.int64])
assert_type(xp.sum(xp.asarray([1.0], dtype=xp.float32)), xp.Array[np.float32])
assert_type(xp.argmax(x), xp.Array[np.intp])
assert_type(xp.unique_all(x).counts, xp.Array[np.intp])
assert_type(x + 1, xp.Array[xp.Scalar])
assert_type(xp.linalg.svd(x).S, xp.Array[xp.Scalar])
assert_type(xp.fft.fft(x), xp.Array[xp.Scalar])
assert_type(x.__array__(), np.ndarray[tuple[int, ...], np.dtype[np.uint8]])
assert_type(xp.iinfo(xp.uint8).max, int)
assert_type(xp.finfo(xp.float32).eps, float)
assert_type(Array([1, 2]).__array__(), np.ndarray[tuple[int, ...], np.dtype[np.uint8]])

def needs_uint8(value: xp.Array[np.uint8]) -> None:
    pass

needs_uint8(unknown)  # type: ignore[arg-type]
unknown.nonexistent()  # type: ignore[attr-defined]
unknown.dtype.nonexistent()  # type: ignore[attr-defined]
T = TypeVar('T', bound=xp.Scalar)
def aggregate(value: xp.Array[T]) -> xp.Array[xp.Scalar]:
    return xp.sum(value)
namespace = x.__array_namespace__()
assert_type(namespace.asarray([1], dtype=xp.uint8), xp.Array[np.uint8])
assert_type(namespace.sum(x), xp.Array[np.uint64])
assert_type(namespace.fft.fft(x), xp.Array[xp.Scalar])
namespace.nonexistent()  # type: ignore[attr-defined]

assert_type(namespace.asarray([1], dtype=namespace.bool), xp.Array[np.bool_])
