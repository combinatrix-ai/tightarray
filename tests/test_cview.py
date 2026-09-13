import gc
import sys
import weakref

import numpy as np
import pytest

from tightarray import Array
from tightarray import array_api as xp
from tightarray._core import _Storage, _APIView


@pytest.mark.parametrize('dtype', [np.uint8, np.bool_, np.int64, np.float64])
def test_scalar_slots_iteration_and_numpy_fallback(dtype):
    values = np.arange(8).astype(dtype)
    a = xp.asarray(values)
    assert [int(x) for x in a] == [int(x) for x in values]
    for i in range(-8, 8):
        assert a[i].shape == ()
        assert int(a[i]) == int(values[i])
        assert float(a[i]) == float(values[i])
    for i in [-9, 8]:
        with pytest.raises(IndexError):
            a[i]
    with pytest.raises(TypeError):
        int(a)
    a[np.int64(3)] = np.int64(1)
    assert int(a[3]) == 1
    for key in [(), Ellipsis]:
        v = a[3]
        v[key] = 0
        assert int(v) == 0


@pytest.mark.parametrize('layout', ['packed', 'word-aligned'])
def test_widening_shared_views_all_widths(layout):
    a = xp.asarray(Array([0] * 2051, bits=1, layout=layout))
    saved = a[2049]
    reverse = a[::-1]
    for bits in range(2, 9):
        reverse[1] = (1 << bits) - 1
        assert a.storage_bits == bits
        assert int(saved) == (1 << bits) - 1
        assert int(a[0]) == int(a[-1]) == 0
    before = np.asarray(a).copy()
    for invalid in [-1, 256, 1 << 100]:
        with pytest.raises(OverflowError):
            a[0] = invalid
        np.testing.assert_array_equal(np.asarray(a), before)
    boolean = xp.asarray([False, True], dtype=xp.bool)
    boolean[0] = 1 << 100
    boolean[1] = -5
    np.testing.assert_array_equal(np.asarray(boolean), [True, True])


def test_c_storage_validation_and_uninitialized_objects():
    s = _Storage(Array([1, 0], bits=1))
    for bits in [0, 9, -1]:
        with pytest.raises(ValueError):
            s.widen(bits)
    with pytest.raises(ValueError):
        s.data = Array([1], bits=1)
    with pytest.raises(TypeError):
        s.data = None
    with pytest.raises(RuntimeError):
        s.__init__(Array([0, 0], bits=1))
    with pytest.raises(TypeError):
        int(_APIView())
    a = xp.asarray([1, 2], dtype=xp.uint8)
    a._offset = sys.maxsize
    with pytest.raises(IndexError):
        a[1]
    with pytest.raises(IndexError):
        a._new_view((2,), (1,), -1)


def test_subclass_gc_and_shared_storage_lifetime():
    class Child(xp.Array):
        pass
    a = Child._from_numpy(np.array([1, 2], dtype=np.uint8))
    v = a[1]
    assert type(v) is Child
    ref = weakref.ref(a)
    a.cycle = a
    del a
    gc.collect()
    assert ref() is None
    assert int(v) == 2
    v[()] = 255
    assert int(v) == 255


@pytest.mark.parametrize('layout', ['packed', 'word-aligned'])
def test_blocked_widening_preserves_every_value(layout):
    rng = np.random.default_rng(192)
    for old in range(1, 8):
        for new in range(old + 1, 9):
            for n in (0, 1, 1023, 1024, 1025, 2051):
                values = rng.integers(0, 1 << old, n, dtype=np.uint8)
                # Also exercise a native root view with a nonzero bit offset.
                s = _Storage(Array(np.concatenate(([0], values, [0])).astype(np.uint8), bits=old, layout=layout)[1:n+1])
                s.widen(new)
                assert s.data.bits == new
                assert s.data.tolist() == values.tolist()


def test_nd_scalar_slots_and_extreme_indices():
    ref = np.arange(120, dtype=np.uint8).reshape(4, 5, 6)
    a = xp.asarray(ref)
    v = xp.permute_dims(a, (2, 0, 1))[::-1, ::-1, ::2]
    expected = ref.transpose(2, 0, 1)[::-1, ::-1, ::2]
    for idx in np.ndindex(v.shape):
        assert int(v[idx]) == int(expected[idx])
        v[idx] = 255
        expected[idx] = 255
    np.testing.assert_array_equal(np.asarray(a), ref)
    for key in [(1 << 100, 0, 0), (0, -1 << 100, 0)]:
        with pytest.raises(IndexError):
            v[key]
    with pytest.raises(IndexError):
        a[0, 0][1 << 100]


def test_empty_mixed_tuple_index_uses_slice_semantics():
    for shape in [(1, 0), (1, 1, 0, 1, 1)]:
        ref = np.empty(shape, dtype=np.uint8)
        a = xp.asarray(ref)
        key = tuple(slice(None) if n == 0 else 0 for n in shape)
        assert a[key].shape == ref[key].shape
        a[key] = 3
        assert np.asarray(a).size == 0
