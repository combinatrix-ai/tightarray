"""Small-integer arrays with packed or word-aligned storage."""
from itertools import chain
from operator import index
from ._core import Array, _Rows

__all__ = ["Array", "Matrix", "RaggedArray"]


class Matrix(_Rows):
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
