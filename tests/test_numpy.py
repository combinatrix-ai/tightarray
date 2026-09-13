import operator

import numpy as np
import pytest

from tightarray import Array, Matrix, RaggedArray


@pytest.fixture(params=[(b, layout, matrix) for b in range(1, 9)
                        for layout in ('packed', 'word-aligned') for matrix in (False, True)])
def pair(request):
    b, layout, matrix = request.param
    ref = (np.arange(24, dtype=np.uint8) % (1 << b)).astype(np.uint8) if b < 8 else np.arange(24, dtype=np.uint8)
    if matrix:
        ref = ref.reshape(4, 6)
        obj = Matrix.from_flat(ref.ravel(), ref.shape, bits=b, layout=layout)
    else:
        obj = Array(ref, bits=b, layout=layout)
    return obj, ref


def test_numpy_conversion_ownership_and_metadata(pair):
    a, ref = pair
    assert a.shape == ref.shape and a.ndim == ref.ndim and a.size == ref.size
    assert a.dtype == ref.dtype
    for dtype in (None, np.int16, np.float64, np.bool_):
        out = np.asarray(a, dtype=dtype)
        np.testing.assert_array_equal(out, ref.astype(dtype) if dtype is not None else ref)
        assert out.flags.writeable
        out.flat[0] = 1
        assert np.asarray(a).flat[0] == ref.flat[0]
    with pytest.raises(ValueError, match='without a copy'):
        np.asarray(a, copy=False)
    np.testing.assert_array_equal(np.array(a, copy=True), ref)
    with pytest.raises(ValueError, match='truth value'):
        bool(a)


def test_numpy_dispatch_and_operators(pair):
    a, ref = pair
    for op in (operator.eq, operator.ne, operator.lt, operator.le, operator.gt,
               operator.ge, operator.add, operator.sub, operator.mul, operator.and_,
               operator.or_, operator.xor, operator.lshift, operator.rshift):
        np.testing.assert_array_equal(op(a, 1), op(ref, 1))
        np.testing.assert_array_equal(op(1, a), op(1, ref))
    np.testing.assert_array_equal(a == a.copy(), ref == ref)
    assert a.equals(a.copy())
    assert np.array_equal(a, a.copy())
    assert np.array_equal(a, ref)
    assert np.array_equal(ref, a)
    assert not np.array_equal(a, np.zeros_like(ref))
    broadcast = np.arange(ref.shape[-1], dtype=np.uint8)
    np.testing.assert_array_equal(np.add(a, broadcast), ref + broadcast)
    np.testing.assert_array_equal(np.add.reduce(a), np.add.reduce(ref))
    np.testing.assert_array_equal(np.add.accumulate(a), np.add.accumulate(ref))
    assert np.count_nonzero(a) == np.count_nonzero(ref)
    for axis in (None, 0, -1):
        for keepdims in (False, True):
            np.testing.assert_array_equal(np.count_nonzero(a, axis=axis, keepdims=keepdims),
                                          np.count_nonzero(ref, axis=axis, keepdims=keepdims))
    for fn in (np.sum, np.prod, np.mean, np.min, np.max, np.all, np.any):
        np.testing.assert_array_equal(fn(a, axis=0), fn(ref, axis=0))
    for fn in (np.concatenate, np.stack):
        np.testing.assert_array_equal(fn([a, a]), fn([ref, ref]))
    np.testing.assert_array_equal(np.transpose(a), ref.T)
    np.testing.assert_array_equal(np.reshape(a, (6, 4)), ref.reshape(6, 4))
    cloned = np.copy(a)
    assert type(cloned) is type(a) and cloned.equals(a)
    np.testing.assert_array_equal(np.copy(a, order='F'), ref)
    out = np.zeros_like(ref)
    assert np.add(a, 1, out=out) is out
    np.testing.assert_array_equal(out, ref + 1)
    with pytest.raises(TypeError):
        np.add(a, 1, out=a)
    with pytest.raises(TypeError):
        np.add.at(a, 0, 1)
    np.testing.assert_array_equal(a, ref)


def test_numpy_take_and_invalid_indices(pair):
    a, ref = pair
    for indices in ([2, -1, 0], np.array([1, 3], dtype=np.intp), [], 1, [[1, 2], [3, 0]]):
        got = np.take(a, indices)
        np.testing.assert_array_equal(got, np.take(ref, indices))
        if isinstance(a, Array) and np.asarray(indices).dtype == np.dtype(np.intp) and np.ndim(indices) == 1:
            assert isinstance(got, Array)
    for mode in ('clip', 'wrap'):
        np.testing.assert_array_equal(np.take(a, [100, -100], mode=mode), np.take(ref, [100, -100], mode=mode))
    with pytest.raises(IndexError):
        np.take(a, [1000])
    out = np.empty(2, dtype=np.uint8)
    assert np.take(a, [0, 1], out=out) is out
    np.testing.assert_array_equal(out, ref.ravel()[:2])


def test_empty_shapes_scalar_truth_and_safety():
    for a in (Array([]), Matrix.from_flat([], (0, 4)), Matrix([[], []])):
        assert np.asarray(a).shape == a.shape
        assert np.count_nonzero(a) == 0
        assert a.equals(a.copy())
    assert bool(Array([1], bits=1)) and not bool(Array([0], bits=1))
    assert bool(Matrix([[1]], bits=1))
    a = Array([0, 1], bits=1)
    with pytest.raises(ValueError):
        _ = a == Array([0, 1, 0], bits=1)
    with pytest.raises(TypeError):
        np.median(a)  # Explicitly outside the registered function set.
    for call in (lambda: np.sum(a, out=a), lambda: np.sum(a, None, None, a)):
        with pytest.raises(TypeError):
            call()
    with pytest.raises(TypeError):
        np.take(a, [0, 1], out=a)
    np.testing.assert_array_equal(np.take(a, Array([1, 0], bits=1)), [1, 0])
    assert a.tolist() == [0, 1]
    r = RaggedArray([[0], [1, 0]], bits=1)
    assert r.equals(r.copy()) and r == r.copy()


def test_foreign_dispatch_is_respected():
    class Foreign:
        def __array_ufunc__(self, ufunc, method, *args, **kwargs):
            return 'foreign'
    a = Array([0, 1], bits=1)
    assert np.add(a, Foreign()) == 'foreign'
    assert a.__array_ufunc__(np.add, '__call__', a, Foreign()) is NotImplemented
    assert a.__array_function__(np.sum, (Foreign,), (a,), {}) is NotImplemented
