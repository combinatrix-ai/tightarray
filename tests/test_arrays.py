import gc
import itertools
import random
import sys

import numpy as np
import pytest

from tightarray import Array, Matrix, RaggedArray


@pytest.fixture(params=itertools.product(range(1, 9), ("packed", "word-aligned")))
def spec(request):
    bits, layout = request.param
    return dict(bits=bits, layout=layout)


def test_roundtrip_boundaries_and_mutation(spec):
    rng = random.Random(719)
    limit = 1 << spec["bits"]
    for n in [0, 1, 7, 8, 9, 12, 13, 31, 32, 63, 64, 65, 127, 129, 1025]:
        values = [rng.randrange(limit) for _ in range(n)]
        a = Array(values, **spec)
        assert a.tolist() == values
        assert a.tobytes() == bytes(values)
        assert list(a) == values
        assert Array(bytes(values), **spec).equals(a)
        assert Array(np.array(values, dtype=np.uint8), **spec).equals(a)
        for i in range(n):
            assert a[i] == values[i] == a[i - n]
            a[i] = limit - 1
            values[i] = limit - 1
        assert a.tolist() == values
        assert a.count(limit - 1) == n
        assert a.count(limit) == a.count(-1) == a.count(1 << 100) == 0


def test_slices_views_and_lifetimes(spec):
    vals = [i % (1 << spec["bits"]) for i in range(157)]
    a = Array(vals, **spec)
    for start, stop, step in itertools.product([None, -200, -1, 0, 3, 12, 64, 157, 200], repeat=3):
        if step == 0:
            continue
        sl = slice(start, stop, step)
        assert a[sl].tolist() == vals[sl]
    v = a[3:130][2:90]
    assert v.base is a
    v[0] = 0
    assert a[5] == 0
    copied = v.copy()
    v[0] = 1
    assert copied[0] == 0
    del a
    gc.collect()
    assert v[0] == 1
    assert v.nbytes == 0


def test_gather_compare_count_find(spec):
    rng = random.Random(93)
    vals = [rng.randrange(1 << spec["bits"]) for _ in range(701)]
    a = Array(vals, **spec)
    assert a.gather([0, -1, 65, 3]).tolist() == [vals[i] for i in [0, -1, 65, 3]]
    assert a.gather(np.array([3, 5], dtype=np.int64)).tolist() == vals[3:6:2]
    for offset in [0, 1, 12, 63, 64, 65]:
        v = a[offset:]
        for val in range(1 << spec["bits"]):
            assert v.count(val) == vals[offset:].count(val)
        for needle in [[], vals[9:12], vals[40:72], vals, [0] * 150, [1]]:
            expected = bytes(vals[offset:]).find(bytes(needle))
            assert v.find(needle) == expected
            assert v.find(Array(needle, **spec)) == expected
        assert v.equals(Array(vals[offset:], bits=8))
        assert v.copy().equals(v)
    assert Array([0], **spec) < Array([1], **spec)
    assert (Array([0], **spec) <= Array([0, 0], **spec)).all()
    assert not Array([], **spec).equals(Array([0], **spec))


def test_invalid_inputs(spec):
    with pytest.raises(ValueError):
        Array([1 << spec["bits"]], **spec)
    with pytest.raises(TypeError):
        Array([1.0], **spec)
    a = Array([0, 1], **spec)
    for i in [2, -3, 10 ** 100]:
        with pytest.raises(IndexError):
            _ = a[i]
        with pytest.raises(IndexError):
            a[i] = 0
        with pytest.raises(IndexError):
            a.gather([i])
    with pytest.raises(TypeError):
        a[0] = 0.1
    with pytest.raises(ValueError):
        a[0] = -1
    with pytest.raises(TypeError):
        del a[0]
    with pytest.raises(ValueError):
        _ = a[::0]
    assert a.tolist() == [0, 1]


def test_nested(spec):
    rows = [[0, 1], [1, 0], [0, 0]]
    m = Matrix(rows, **spec)
    assert m.shape == (3, 2)
    assert m.tolist() == rows
    assert m[-2, -2] == 1
    m[0, 1] = 0
    assert m[0].tolist() == [0, 0]
    m[1][0] = 0
    assert m.count(1) == 0
    assert m.copy().equals(m)
    assert Matrix.from_flat([0, 1, 1, 0], (2, 2), **spec).tolist() == rows[:2]
    assert Matrix([[], []], **spec).shape == (2, 0)
    assert Matrix.from_flat([], (0, 10), **spec).shape == (0, 10)
    with pytest.raises(ValueError):
        Matrix([[0], [0, 1]], **spec)
    with pytest.raises(IndexError):
        _ = m[0, 2]
    r = RaggedArray([[], [0, 1], [], [1], []], **spec)
    assert r.tolist() == [[], [0, 1], [], [1], []]
    assert r[1, -1] == 1
    r[1, 0] = 1
    assert r.count(1) == 3
    assert r.copy() == r
    assert r != RaggedArray([[1, 1, 1]], **spec)
    for start, stop, step in itertools.product([None, -20, -1, 0, 2, 4, 20], repeat=3):
        if step == 0:
            continue
        sl = slice(start, stop, step)
        assert m[sl].tolist() == m.tolist()[sl]
        assert r[sl].tolist() == r.tolist()[sl]
    v = r[1:4]
    v[0, 0] = 0
    assert r[1, 0] == 0
    assert sys.getsizeof(r) > r.nbytes


def test_constructor_edges():
    for bits in [0, 9, -1]:
        with pytest.raises(ValueError):
            Array([], bits=bits)
    with pytest.raises(ValueError):
        Array([], layout="aligned")
    assert Array(np.arange(10, dtype=np.uint8)[::2]).tolist() == [0, 2, 4, 6, 8]
    assert Array(memoryview(b"abcd")[::2]).tobytes() == b"ac"
    with pytest.raises(ValueError):
        Matrix.from_flat([0], (0, 0))
    with pytest.raises(ValueError):
        Matrix.from_flat([], (-1, 0))


def test_randomized_views_search_and_cross_layout(spec):
    rng = random.Random(1258)
    limit = 1 << spec["bits"]
    for trial in range(120):
        values = [rng.randrange(limit) for _ in range(rng.randrange(200))]
        a = Array(bytes(values), **spec)
        start, stop = sorted([rng.randrange(len(values) + 1) for _ in range(2)])
        v, ref = a[start:stop], values[start:stop]
        assert v.copy().tolist() == ref
        assert v.equals(Array(ref, bits=spec["bits"], layout="word-aligned" if spec["layout"] == "packed" else "packed"))
        if ref:
            different = list(ref)
            different[-1] ^= 1
            assert not v.equals(Array(different, **spec))
        for size in [0, 1, 2, 7, 8, 9, 12, 13, 32, 64, 65]:
            needle = [rng.randrange(limit) for _ in range(size)]
            assert v.find(needle) == bytes(ref).find(bytes(needle))
        for value in {0, limit - 1, rng.randrange(limit)}:
            assert v.count(value) == ref.count(value)
    for n in [0, 1, 63, 64, 65, 129]:
        values = bytes([limit - 1]) * n
        a = Array(values, **spec)
        for k in range(70):
            assert a.find(bytes([limit - 1]) * k) == values.find(bytes([limit - 1]) * k)
            assert a.find(bytes([limit - 1]) * k + b"\0") == -1


def test_reentrant_input_and_uninitialized_containers():
    source = []
    class ClearsList:
        def __index__(self):
            source.clear()
            return 1
    source.extend([ClearsList(), 0, 1])
    assert Array(source, bits=2).tolist() == [1, 0, 1]
    source.extend([ClearsList(), 0, 1])
    assert Array([0, 1], bits=2).gather(source).tolist() == [1, 0, 1]
    for cls in [Matrix, RaggedArray]:
        obj = cls.__new__(cls)
        for operation in [lambda: len(obj), lambda: obj[0], lambda: obj.count(0), lambda: obj.tolist(), lambda: obj.copy(), lambda: obj.shape]:
            with pytest.raises(RuntimeError):
                operation()
        assert sys.getsizeof(obj) > 0
        obj.__init__([[0]])
        with pytest.raises(RuntimeError):
            obj.__init__([[1]])
        assert obj.tolist() == [[0]]


def test_view_keeps_original_container_data_alive():
    for cls in [Matrix, RaggedArray]:
        original = cls([[0, 1], [1, 0]], bits=2)
        row, rows = original[1], original[:]
        del original
        gc.collect()
        row[0] = 0
        assert rows[1, 0] == 0
        assert rows.copy().tolist() == [[0, 1], [0, 0]]


def test_flat_ragged_and_invalid_native_shapes():
    from tightarray._core import _Rows
    assert RaggedArray.from_flat(bytes([1, 2, 3]), [0, 0, 2, 3], bits=2).tolist() == [[], [1, 2], [3]]
    assert RaggedArray.from_flat([], [0]).tolist() == []
    for offsets in [[], [1], [0, 2], [0, -1, 1], [0, 1, 0, 1], [0, 1 << 100]]:
        with pytest.raises((ValueError, OverflowError)):
            RaggedArray.from_flat([0], offsets)
    for args in [(Array([]), -1, 0), (Array([]), 1, -1), (Array([]), 1 << 62, 8), (Array([]), 0, 0, [0, 0])]:
        with pytest.raises((ValueError, OverflowError)):
            _Rows(*args)


def test_native_gather_buffers(spec):
    rng = random.Random(881)
    values = [rng.randrange(1 << spec['bits']) for _ in range(301)]
    a = Array(values, **spec)[3:299]
    values = values[3:299]
    for n in [0, 1, 7, 8, 9, 64, 257]:
        idx = np.array([rng.randrange(-len(a), len(a)) for _ in range(n)], dtype=np.intp)
        assert a.gather(idx).tolist() == [values[i] for i in idx]
        raw = bytearray(1 + idx.nbytes)
        unaligned = np.ndarray(idx.shape, dtype=np.intp, buffer=raw, offset=1)
        unaligned[:] = idx
        assert a.gather(unaligned).tolist() == [values[i] for i in idx]
        assert a.gather(idx[::-1]).tolist() == [values[i] for i in idx[::-1]]
    for idx in [len(a), -len(a)-1, np.iinfo(np.intp).min, np.iinfo(np.intp).max]:
        with pytest.raises(IndexError):
            a.gather(np.array([0, idx], dtype=np.intp))


def test_simd_pack_validation_and_copy_edges(spec):
    bits = spec['bits']
    for n in range(145):
        values = bytes(i % (1 << bits) for i in range(n))
        a = Array(values, **spec)
        assert a.tobytes() == values
        for start in [0, 1, 7, 9, 13, 63]:
            assert a[start:].copy().tobytes() == values[start:]
        if bits < 8:
            for at in {0, n // 2, n - 1}:
                if at >= 0 and n:
                    bad = bytearray(values)
                    bad[at] = 1 << bits
                    with pytest.raises(ValueError):
                        Array(bad, **spec)
