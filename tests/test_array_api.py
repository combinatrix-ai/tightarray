import numpy as np
import pytest
from tightarray import Array as NativeArray
from tightarray import array_api as xp


@pytest.mark.parametrize('layout', ['packed', 'word-aligned'])
@pytest.mark.parametrize('bits', range(1, 9))
def test_native_bridge_preserves_packing_and_isolation(bits, layout):
    native = NativeArray(bytes(i % (1 << bits) for i in range(256)), bits=bits, layout=layout)
    a = xp.asarray(native)
    assert a.__array_namespace__() is xp
    assert a.storage_bits == bits
    assert a._storage.data.layout == layout
    assert a._numpy is None
    np.testing.assert_array_equal(np.asarray(a), native.tolist())
    a[0] = 255
    assert native[0] == 0
    assert int(a[0]) == 255
    with pytest.raises(ValueError):
        xp.asarray(native, copy=False)


def test_packed_nd_views_and_shared_widening():
    a = xp.reshape(xp.asarray([0, 1, 2, 3] * 24, dtype=xp.uint8), (4, 6, 4))
    assert a._numpy is None and a.storage_bits == 2 and a.storage_nbytes == 24
    view = a[::-1, 1::2, ::-1]
    assert view._storage is a._storage
    ref = np.asarray(a)
    view[0, 0, 0] = 255
    ref[::-1, 1::2, ::-1][0, 0, 0] = 255
    assert a.storage_bits == view.storage_bits == 8
    np.testing.assert_array_equal(np.asarray(a), ref)
    transposed = xp.permute_dims(a, (2, 0, 1))
    transposed[0, 0, 0] = 111
    assert int(a[0, 0, 0]) == 111
    assert xp.asarray(a, copy=False) is a
    clone = xp.asarray(a, copy=True)
    assert clone._storage is not a._storage


def test_boolean_results_scalar_arrays_and_promotion():
    a = xp.asarray(np.tile([0, 1, 2, 3], 4096), dtype=xp.uint8)
    mask = a > 1
    assert isinstance(mask, xp.Array) and mask.dtype == xp.bool
    assert mask.storage_bits == 1 and mask.storage_nbytes == a.size // 8
    assert a.storage_nbytes == a.size // 4
    assert a[0].shape == () and int(a[1]) == 1
    assert bool(mask[2])
    with pytest.raises(TypeError):
        bool(mask)
    total = xp.sum(a)
    assert total.dtype == xp.uint64 and total.shape == ()
    assert total._numpy is not None and int(total) == 24576


def test_dlpack_copy_contract():
    a = xp.asarray([0, 1, 2, 3], dtype=xp.uint8)
    for copy in [None, True]:
        b = np.from_dlpack(a, copy=copy)
        np.testing.assert_array_equal(b, [0, 1, 2, 3])
    with pytest.raises(BufferError):
        a.__dlpack__(copy=False)
    assert xp.from_dlpack(a, copy=False) is a


def test_namespace_version():
    a = xp.asarray(1)
    assert a.__array_namespace__(api_version='2025.12') is xp
    with pytest.raises(ValueError):
        a.__array_namespace__(api_version='2099.12')


def test_external_copy_contracts_and_native_dtype():
    source = np.arange(4, dtype=np.float64)
    copied = xp.asarray(source, copy=True)
    source[0] = 99
    assert float(copied[0]) == 0
    native = xp.asarray(NativeArray([0, 1], bits=1))
    assert xp.astype(native, xp.float32).dtype == xp.float32
    with pytest.raises(BufferError):
        xp.from_dlpack(np.arange(4, dtype=np.uint8), copy=False)
    shared = xp.from_dlpack(source, copy=False)
    source[1] = 42
    assert float(shared[1]) == 42


def test_atanh_nan_real_finite_imaginary():
    with np.errstate(invalid='ignore'):
        result = complex(xp.atanh(xp.asarray(complex(float('nan'), 8.976879890218818e153))))
    assert np.isnan(result.real) and np.isnan(result.imag)
