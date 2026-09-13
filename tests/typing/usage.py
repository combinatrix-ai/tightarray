from typing_extensions import assert_type
import numpy as np
from tightarray import Array, Matrix, RaggedArray
from tightarray import array_api as xp

a = Array([0, 1, 3], bits=2, layout='packed')
assert_type(a[0], int)
assert_type(a[1:], Array)
assert_type(a.sum(), int)
assert_type(a.tolist(), list[int])
assert_type(a.gather([2, 0]), Array)
assert_type(a.shape, tuple[int])
assert_type(a.dtype, np.dtype[np.uint8])
assert_type(a.bits, int)
a[0] = np.uint8(2)
m = Matrix.from_flat([1, 2, 3, 4], (2, 2), bits=3)
assert_type(m[0], Array)
assert_type(m[0, 0], int)
assert_type(m[:1], Matrix)
assert_type(m.shape, tuple[int, int])
r = RaggedArray([[1], [], [2, 3]], bits=2)
assert_type(r[1:], RaggedArray)
assert_type(r.tolist(), list[list[int]])
assert_type(r.shape, tuple[int, None])
x = xp.reshape(xp.asarray(a), (1, 3))
assert_type(x[0, 0], xp.Array[np.uint8])
assert_type(x[:, ::2], xp.Array[np.uint8])
assert_type(x + 1, xp.Array[xp.Scalar])
assert_type(x > 1, xp.Array[np.bool_])
assert_type(xp.sum(x, axis=0), xp.Array[np.uint64])
assert_type(xp.sum(x, axis=(0, 1), dtype=xp.uint64), xp.Array[np.uint64])
assert_type(xp.zeros((2, 3), dtype=xp.uint8), xp.Array[np.uint8])
assert_type(xp.nonzero(x), tuple[xp.Array[np.intp], ...])
assert_type(xp.unique_all(x).counts, xp.Array[np.intp])
assert_type(xp.broadcast_shapes((2, 1), (3,)), tuple[int, ...])
assert_type(xp.can_cast(xp.uint8, xp.uint16), bool)
assert_type(x.storage_bits, int)
assert_type(x.shape, tuple[int, ...])
assert_type(xp.set_strict(True), None)
with xp.strict():
    x[0, 0] = 1

# Each ignore must suppress the specified error; unused ignores fail this suite.
Array([1], bits=9)  # type: ignore[arg-type]
Array([1], layout='dense')  # type: ignore[arg-type]
a[0] = 'bad'  # type: ignore[assignment]
a[0:1] = 1  # type: ignore[index]
m[0, 0] = 1.5  # type: ignore[assignment]
xp.set_strict('yes')  # type: ignore[arg-type]
xp.sum(x, axis='rows')  # type: ignore[call-overload]
xp.reshape(x, ('bad',))  # type: ignore[arg-type]
xp.zeros('bad')  # type: ignore[call-overload]
wrong: int = x[0]  # type: ignore[assignment]
x.storage_bits = 5  # type: ignore[misc]

assert_type(xp.linalg.eigh(x).eigenvalues, xp.Array[xp.Scalar])
assert_type(xp.linalg.svd(x).S, xp.Array[xp.Scalar])
assert_type(xp.fft.fft(x), xp.Array[xp.Scalar])
assert_type(xp.fft.fftfreq(8), xp.Array[xp.Scalar])
assert_type(xp.__array_namespace_info__().devices(), tuple[str, ...])
xp.fft.fft(x, axis='bad')  # type: ignore[arg-type]
