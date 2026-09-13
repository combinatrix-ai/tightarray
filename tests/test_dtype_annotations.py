from typing import get_args, get_origin, get_type_hints
import numpy as np
import pytest
from tightarray import array_api as xp


def typed_consumer(x: xp.Array[xp.uint8]) -> xp.Array[xp.float32]:
    return xp.astype(x, xp.float32)


def test_evaluated_annotations_and_widening():
    hints = get_type_hints(typed_consumer)
    assert get_origin(hints['x']) is xp.Array
    assert get_args(hints['x']) == (np.uint8,)
    assert get_args(hints['return']) == (np.float32,)
    x = xp.asarray([0, 1, 7], dtype=xp.uint8)
    view = x[::-1]
    assert x.storage_bits == 3
    with pytest.warns(xp.StorageWideningWarning):
        view[0] = 31
    assert x.storage_bits == view.storage_bits == 5
    assert x.dtype == view.dtype == np.dtype(np.uint8)
    assert typed_consumer(x).dtype == np.dtype(np.float32)
    assert (x > 1).dtype == np.dtype(np.bool_)
    assert xp.sum(x, dtype=xp.uint64).dtype == np.dtype(np.uint64)


@pytest.mark.parametrize('dtype', [xp.bool, xp.uint8, xp.uint16, xp.uint32, xp.uint64,
    xp.int8, xp.int16, xp.int32, xp.int64, xp.float32, xp.float64, xp.complex64, xp.complex128])
def test_dtype_preserving_operations(dtype):
    x = xp.asarray([0, 1], dtype=dtype)
    assert get_args(xp.Array[dtype]) == (dtype,)
    for result in [x[0], x[:], xp.reshape(x, (1, 2)).T,
                   xp.permute_dims(x, (0,)), xp.zeros_like(x), xp.asarray(x)]:
        assert result.dtype == np.dtype(dtype)
