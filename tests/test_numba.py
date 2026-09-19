import gc

import numpy as np
import pytest

numba = pytest.importorskip("numba")
from tightarray import Array
from tightarray.numba import as_native, load, store


@numba.njit
def copy_and_increment(source, target):
    for i in range(source.length):
        store(target, i, (load(source, i) + 1) % (1 << source.bits))


@pytest.mark.parametrize("bits", range(1, 9))
@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
def test_native_roundtrip_and_views(bits, layout):
    rng = np.random.default_rng(bits)
    values = rng.integers(0, 1 << bits, 137, dtype=np.uint8)
    source = Array(values, bits=bits, layout=layout)
    target = Array(np.zeros(139, dtype=np.uint8), bits=bits, layout=layout)
    native = as_native(source[1:136])
    output = as_native(target[2:137])
    copy_and_increment(native, output)
    expected = (values[1:136].astype(np.uint16) + 1) % (1 << bits)
    np.testing.assert_array_equal(np.asarray(target)[2:137], expected)
    assert target[0] == target[1] == target[137] == target[138] == 0
    assert load(native, -1) == values[135]
    # The borrowed buffer remains valid after every original Python reference dies.
    del source
    gc.collect()
    assert load(native, 0) == values[1]
    # Aliasing is real, not a decoded/copy-on-write buffer.
    store(output, 0, (1 << bits) - 1)
    assert target[2] == (1 << bits) - 1


def test_errors_are_before_mutation():
    array = Array([1] * 30, bits=3)
    native = as_native(array)
    before = array.tobytes()
    for value in [-1, 8, 2**32]:
        with pytest.raises(ValueError):
            store(native, 21, value)  # This index crosses a 64-bit word boundary.
        assert array.tobytes() == before
    for index in [-31, 30]:
        with pytest.raises(IndexError):
            load(native, index)
        with pytest.raises(IndexError):
            store(native, index, 0)
    empty = as_native(Array([], bits=1))
    with pytest.raises(IndexError):
        load(empty, 0)
    with pytest.raises(TypeError):
        as_native(np.array([1]))


def test_zero_copy_and_numpy_logical_contract():
    array = Array([1, 2, 3], bits=2)
    first, second = as_native(array), as_native(array)
    assert np.shares_memory(first.words, second.words)
    array[0] = 3
    assert load(first, 0) == 3
    np.testing.assert_array_equal(np.asarray(array), [3, 2, 3])
    # Publishing a physical Array buffer would incorrectly bypass __array__.
    with pytest.raises(TypeError):
        memoryview(array)


@pytest.mark.parametrize("bits", range(1, 9))
@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
def test_specializations_do_not_mix_widths(bits, layout):
    from tightarray.numba import specialize

    read, write = specialize(bits, layout)
    values = (np.arange(129, dtype=np.uint16) % (1 << bits)).astype(np.uint8)
    array = Array(values, bits=bits, layout=layout)
    native = as_native(array[1:])

    @numba.njit
    def update(a):
        for i in range(a.length):
            write(a, i, (read(a, i) + 1) % (1 << bits))

    update(native)
    np.testing.assert_array_equal(
        np.asarray(array)[1:], (values[1:].astype(np.uint16) + 1) % (1 << bits)
    )
    other = as_native(Array([0], bits=2 if bits == 1 else 1, layout=layout))
    with pytest.raises(ValueError):
        read(other, 0)
    with pytest.raises(ValueError):
        write(other, 0, 0)


def test_floating_values_are_not_silently_truncated():
    from tightarray.numba import specialize

    a = Array([0], bits=2)
    native = as_native(a)
    _, write = specialize(2)
    for value in [1.5, 1.0, np.float32(1.5), float("nan")]:
        with pytest.raises(TypeError):
            store(native, 0, value)
        with pytest.raises(TypeError):
            write(native, 0, value)
        assert a[0] == 0
