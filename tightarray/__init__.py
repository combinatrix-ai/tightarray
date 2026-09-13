"""Small-integer arrays with packed or word-aligned storage."""
from array import array as _offset_array
from itertools import chain
from operator import index
import sys

from ._core import Array

__all__ = ["Array", "Matrix", "RaggedArray"]


def _index(value, length):
    value = index(value)
    if value < 0:
        value += length
    if not 0 <= value < length:
        raise IndexError("index out of range")
    return value


class Matrix:
    """Rectangular rows sharing one native data buffer; row access returns a view."""
    __slots__ = ("_data", "_rows", "_cols")

    def __init__(self, rows, *, bits=8, layout="packed"):
        rows = [tuple(row) for row in rows]
        cols = len(rows[0]) if rows else 0
        if any(len(row) != cols for row in rows):
            raise ValueError("matrix rows must have equal lengths")
        self._data = Array(chain.from_iterable(rows), bits=bits, layout=layout)
        self._rows, self._cols = len(rows), cols

    @classmethod
    def from_flat(cls, values, shape, *, bits=8, layout="packed"):
        rows, cols = map(index, shape)
        if rows < 0 or cols < 0:
            raise ValueError("shape dimensions must be nonnegative")
        data = Array(values, bits=bits, layout=layout)
        if len(data) != rows * cols:
            raise ValueError("shape does not match data length")
        obj = object.__new__(cls)
        obj._data, obj._rows, obj._cols = data, rows, cols
        return obj

    @property
    def shape(self):
        return self._rows, self._cols

    @property
    def bits(self):
        return self._data.bits

    @property
    def layout(self):
        return self._data.layout

    @property
    def nbytes(self):
        return self._data.nbytes

    def __len__(self):
        return self._rows

    def __getitem__(self, key):
        if isinstance(key, tuple):
            row, col = key
            return self._data[_index(row, self._rows) * self._cols + _index(col, self._cols)]
        if isinstance(key, slice):
            start, stop, step = key.indices(self._rows)
            if step != 1:
                return Matrix((self[i] for i in range(start, stop, step)), bits=self.bits, layout=self.layout)
            obj = object.__new__(Matrix)
            obj._rows, obj._cols = max(0, stop - start), self._cols
            obj._data = self._data[start * self._cols:stop * self._cols]
            return obj
        row = _index(key, self._rows)
        return self._data[row * self._cols:(row + 1) * self._cols]

    def __setitem__(self, key, value):
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("assignment requires matrix[row, col]")
        row, col = key
        self._data[_index(row, self._rows) * self._cols + _index(col, self._cols)] = value

    def __eq__(self, other):
        if not isinstance(other, Matrix):
            return NotImplemented
        return self.shape == other.shape and self._data == other._data

    def count(self, value):
        return self._data.count(value)

    def copy(self):
        obj = object.__new__(Matrix)
        obj._data, obj._rows, obj._cols = self._data.copy(), self._rows, self._cols
        return obj

    def tolist(self):
        return [row.tolist() for row in self]

    def __sizeof__(self):
        return object.__sizeof__(self) + retained_size(self._data) + sys.getsizeof(self._rows) + sys.getsizeof(self._cols)


class RaggedArray:
    """Variable-length rows stored as packed data plus a uint64 offsets buffer."""
    __slots__ = ("_data", "_offsets")

    def __init__(self, rows, *, bits=8, layout="packed"):
        rows = [tuple(row) for row in rows]
        offsets = _offset_array("Q", [0])
        for row in rows:
            offsets.append(offsets[-1] + len(row))
        self._data = Array(chain.from_iterable(rows), bits=bits, layout=layout)
        self._offsets = offsets

    @property
    def bits(self):
        return self._data.bits

    @property
    def layout(self):
        return self._data.layout

    @property
    def nbytes(self):
        return self._data.nbytes + len(self._offsets) * self._offsets.itemsize

    def __len__(self):
        return len(self._offsets) - 1

    def __getitem__(self, key):
        if isinstance(key, tuple):
            row, col = key
            row = _index(row, len(self))
            start, stop = self._offsets[row:row + 2]
            return self._data[start + _index(col, stop - start)]
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step != 1:
                return RaggedArray((self[i] for i in range(start, stop, step)), bits=self.bits, layout=self.layout)
            obj = object.__new__(RaggedArray)
            end = max(start, stop)
            base = self._offsets[start]
            obj._data = self._data[base:self._offsets[end]]
            obj._offsets = _offset_array("Q", (x - base for x in self._offsets[start:end + 1]))
            return obj
        row = _index(key, len(self))
        return self._data[self._offsets[row]:self._offsets[row + 1]]

    def __setitem__(self, key, value):
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("assignment requires ragged[row, col]")
        row, col = key
        row = _index(row, len(self))
        start, stop = self._offsets[row:row + 2]
        self._data[start + _index(col, stop - start)] = value

    def __eq__(self, other):
        if not isinstance(other, RaggedArray):
            return NotImplemented
        return self._offsets == other._offsets and self._data == other._data

    def count(self, value):
        return self._data.count(value)

    def copy(self):
        obj = object.__new__(RaggedArray)
        obj._data, obj._offsets = self._data.copy(), self._offsets[:]
        return obj

    def tolist(self):
        return [row.tolist() for row in self]

    def __sizeof__(self):
        return object.__sizeof__(self) + retained_size(self._data) + sys.getsizeof(self._offsets)


def retained_size(data):
    """Size of an Array view plus the root allocation it keeps alive."""
    return sys.getsizeof(data) + (sys.getsizeof(data.base) if data.base is not None else 0)
