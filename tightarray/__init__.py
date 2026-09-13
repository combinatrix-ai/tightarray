"""Small-integer arrays with packed or word-aligned storage."""
from itertools import chain
from operator import index
from ._core import Array, _Rows

__all__ = ["Array", "Matrix", "RaggedArray"]


class _ArrayInterop:
    __slots__ = ()

    def __array__(self, dtype=None, copy=None):
        from ._numpy import asarray
        return asarray(self, dtype=dtype, copy=copy)

    def __array_ufunc__(self, function, method, *inputs, **kwargs):
        from ._numpy import ufunc
        return ufunc(self, function, method, *inputs, **kwargs)

    def __array_function__(self, function, types, args, kwargs):
        from ._numpy import array_function
        return array_function(self, function, types, args, kwargs)

    @property
    def ndim(self):
        return 2

    @property
    def size(self):
        return self.shape[0] * self.shape[1]

    @property
    def dtype(self):
        from ._numpy import dtype
        return dtype()

    def __bool__(self):
        if self.size != 1:
            raise ValueError('truth value requires exactly one element; use any/all or equals')
        return bool(self[0, 0])


def _binary_operator(name, reflected=False):
    def operation(self, other):
        from ._numpy import binary
        return binary(other, self, name) if reflected else binary(self, other, name)
    return operation


for _name, _ufunc in {'eq': 'equal', 'ne': 'not_equal', 'lt': 'less',
                     'le': 'less_equal', 'gt': 'greater', 'ge': 'greater_equal',
                     'add': 'add', 'sub': 'subtract', 'mul': 'multiply',
                     'truediv': 'true_divide', 'floordiv': 'floor_divide',
                     'mod': 'remainder', 'and': 'bitwise_and', 'or': 'bitwise_or',
                     'xor': 'bitwise_xor', 'lshift': 'left_shift', 'rshift': 'right_shift'}.items():
    setattr(_ArrayInterop, f'__{_name}__', _binary_operator(_ufunc))
    if _name not in ('eq', 'ne', 'lt', 'le', 'gt', 'ge'):
        setattr(_ArrayInterop, f'__r{_name}__', _binary_operator(_ufunc, True))


class Matrix(_ArrayInterop, _Rows):
    """Rectangular rows sharing one native buffer; row access returns a view."""
    __slots__ = ()

    def __init__(self, rows, *, bits=8, layout="packed"):
        rows = [tuple(row) for row in rows]
        cols = len(rows[0]) if rows else 0
        if any(len(row) != cols for row in rows):
            raise ValueError("matrix rows must have equal lengths")
        data = Array(chain.from_iterable(rows), bits=bits, layout=layout)
        super().__init__(data, len(rows), cols)

    @classmethod
    def from_flat(cls, values, shape, *, bits=8, layout="packed"):
        rows, cols = map(index, shape)
        if rows < 0 or cols < 0:
            raise ValueError("shape dimensions must be nonnegative")
        data = Array(values, bits=bits, layout=layout)
        obj = cls.__new__(cls)
        _Rows.__init__(obj, data, rows, cols)
        return obj


class RaggedArray(_Rows):
    """Variable-length rows stored as packed data plus native offsets."""
    __slots__ = ()

    def __init__(self, rows, *, bits=8, layout="packed"):
        rows = [tuple(row) for row in rows]
        offsets = [0]
        for row in rows:
            offsets.append(offsets[-1] + len(row))
        data = Array(chain.from_iterable(rows), bits=bits, layout=layout)
        super().__init__(data, len(rows), 0, offsets)

    @classmethod
    def from_flat(cls, values, offsets, *, bits=8, layout="packed"):
        """Build from flat values and monotone offsets, starting at zero."""
        offsets = tuple(offsets)
        if not offsets:
            raise ValueError("offsets must contain at least zero")
        data = Array(values, bits=bits, layout=layout)
        obj = cls.__new__(cls)
        _Rows.__init__(obj, data, len(offsets) - 1, 0, offsets)
        return obj
