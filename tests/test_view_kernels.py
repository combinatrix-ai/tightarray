import itertools
import sys

import numpy as np
import pytest

from tightarray import Array
import tightarray.array_api as xp


@pytest.mark.parametrize('bits,layout', list(itertools.product(range(1, 9), ('packed', 'word-aligned'))))
def test_sum_and_unpack_shifted_storage(bits, layout):
    ref = np.arange(2300, dtype=np.uint64).astype(np.uint8) & ((1 << bits) - 1)
    root = Array(ref, bits=bits, layout=layout)
    for start in (0, 1, 7, 12, 63, 64, 65):
        for n in (0, 1, 15, 16, 63, 64, 65, 1023, 1024, 1025, 2100):
            a = root[start:start+n]
            expected = ref[start:start+n]
            assert a.sum() == int(expected.sum(dtype=np.uint64))
            assert a._view_sum((n,), (1,), 0) == a.sum()
            assert a._view_bytes((n,), (1,), 0) == expected.tobytes()
    a = root[7:]
    for shape, strides, offset in [((5, 7), (17, -2), 20), ((3, 9), (0, 1), 4), ((), (), 3)]:
        expected = np.ndarray(shape, dtype=np.uint8, buffer=ref[7:].copy(), offset=offset, strides=strides)
        assert a._view_bytes(shape, strides, offset) == expected.tobytes()
        assert a._view_sum(shape, strides, offset) == int(expected.sum(dtype=np.uint64))
    for stride in (-17, -3, -1, 0, 1, 3, 17):
        offset = 2000 if stride < 0 else 1
        positions = offset + np.arange(100) * stride
        assert a._view_sum((100,), (stride,), offset) == int(ref[7:][positions].sum(dtype=np.uint64))
    rng = np.random.default_rng(11)
    for _ in range(10):
        values = rng.integers(0, 1 << bits, size=4097, dtype=np.uint8)
        assert Array(values, bits=bits, layout=layout).sum() == int(values.sum(dtype=np.uint64))


@pytest.mark.parametrize('shape,strides,offset', [((-1,), (1,), 0), ((2,), (), 0), ((2,), (1,), -1), ((2,), (1,), 7), ((2,), (-1,), 0), ((sys.maxsize, 2), (1, 1), 0), ((2,), (sys.maxsize,), 0), ((1,)*65, (1,)*65, 0)])
def test_invalid_descriptors_do_not_mutate(shape, strides, offset):
    a = Array(range(8), bits=3)
    before = a.tobytes()
    for method in (a._view_bytes, a._view_sum):
        with pytest.raises((ValueError, IndexError, OverflowError)):
            method(shape, strides, offset)
    with pytest.raises((ValueError, IndexError, OverflowError)):
        a._view_assign(shape, strides, offset, b'\x00\x01')
    assert a.tobytes() == before


def test_scatter_validation_empty_and_overlap():
    a = Array(range(8), bits=3)
    for data in (b'\x01', b'\x01\xff'):
        with pytest.raises(ValueError):
            a._view_assign((2,), (1,), 0, data)
        assert a.tolist() == list(range(8))
    a._view_assign((2, 2), (4, -1), 1, bytes([7, 6, 5, 4]))
    assert a.tolist() == [6, 7, 2, 3, 4, 5, 6, 7]
    assert a._view_bytes((0,), (-1,), -999) == b''
    assert a._view_sum((0,), (-1,), -999) == 0
    a._view_assign((0,), (-1,), -999, b'')
    a._view_assign((3,), (0,), 2, bytes([1, 2, 3]))
    assert a[2] == 3


def test_shared_views_widen_overlap_and_bulk_assignment():
    ref = np.arange(24, dtype=np.uint8).reshape(4, 6) % 8
    a = xp.asarray(ref)
    view = a[::-1, ::2]
    scalar = view[0, 0]
    view[0, 0] = 200
    ref[-1, 0] = 200
    assert int(scalar) == 200
    assert a.storage_bits == view.storage_bits == 8
    a[:, 1:] = a[:, :-1]
    ref[:, 1:] = ref[:, :-1]
    view[:, ::-1] = xp.asarray(np.full((4, 3), 99, dtype=np.uint8))
    ref[::-1, ::2][:, ::-1] = 99
    np.testing.assert_array_equal(np.asarray(a), ref)
    assert int(xp.sum(view)) == int(ref[::-1, ::2].sum())
    assert xp.sum(view, keepdims=True).shape == (1, 1)
    assert xp.sum(a, dtype=xp.uint8).dtype == np.dtype('uint8')
    np.testing.assert_array_equal(np.asarray(xp.sum(a, axis=0)), ref.sum(axis=0))
    assert np.asarray(a[:0, ::-1]).shape == (0, 6)


def test_assignment_cast_failure_is_atomic():
    a = xp.asarray(np.arange(8, dtype=np.uint8))
    with pytest.raises((ValueError, OverflowError)):
        a[::2] = [1, 2, 3, 999]
    np.testing.assert_array_equal(np.asarray(a), np.arange(8, dtype=np.uint8))


@pytest.mark.parametrize('dtype', (np.uint8, np.bool_))
def test_nd_reductions_and_dtype(dtype):
    ref = (np.arange(120, dtype=np.uint8) % 8).reshape(4, 5, 6).astype(dtype)
    a = xp.asarray(ref)
    for axes in itertools.permutations(range(3)):
        v = xp.permute_dims(a, axes)[::-1, ::2, ::-1]
        expected = np.transpose(ref, axes)[::-1, ::2, ::-1]
        result = xp.sum(v)
        assert int(result) == int(expected.sum())
        assert result.dtype == expected.sum().dtype
        assert int(xp.sum(v, dtype=xp.uint64)) == int(expected.sum())
    assert int(xp.sum(a[:0])) == 0
    assert int(xp.sum(a[0, 0, 0])) == int(ref[0, 0, 0])
