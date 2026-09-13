"""Optional NumPy dispatch; the native storage module does not import NumPy."""
import numpy as np
from ._core import Array


def dtype():
    return np.dtype(np.uint8)


def _supported(value):
    from . import Matrix
    return isinstance(value, (Array, Matrix))


def asarray(self, dtype=None, copy=None):
    if copy is False:
        raise ValueError("tightarray cannot expose its logical elements without a copy")
    # bytearray gives NumPy a writable, independent buffer without a second copy.
    result = np.frombuffer(bytearray(self.tobytes()), dtype=np.uint8).reshape(self.shape)
    if dtype is not None:
        result = result.astype(dtype, copy=False)
    return result


def _convert(value):
    if _supported(value):
        return asarray(value)
    if isinstance(value, tuple):
        return tuple(_convert(v) for v in value)
    if isinstance(value, list):
        return [_convert(v) for v in value]
    if isinstance(value, dict):
        return {k: _convert(v) for k, v in value.items()}
    return value


def _foreign(value):
    if isinstance(value, (tuple, list)):
        return any(_foreign(v) for v in value)
    return (hasattr(value, '__array_ufunc__') and
            not _supported(value) and type(value) is not np.ndarray and
            not isinstance(value, np.generic))


def ufunc(self, function, method, *inputs, **kwargs):
    if any(_foreign(v) for v in (*inputs, kwargs.get('out', ()), kwargs.get('where', True))):
        return NotImplemented
    if any(_supported(v) for v in kwargs.get('out', ())):
        return NotImplemented
    # Never mutate an unpacked temporary instead of the user's packed array.
    if method == 'at' and _supported(inputs[0]):
        return NotImplemented
    return getattr(function, method)(*_convert(inputs), **_convert(kwargs))


def compare(left, right, op):
    return (np.less, np.less_equal, np.equal, np.not_equal, np.greater, np.greater_equal)[op](left, right)


def binary(left, right, name):
    return getattr(np, name)(left, right)


def unary(value, name):
    return getattr(np, name)(value)


def _array_equal(a1, a2, equal_nan=False):
    if _supported(a1) and _supported(a2):
        return a1.equals(a2)
    return np.array_equal(_convert(a1), _convert(a2), equal_nan=equal_nan)


def _copy(a, order='K', subok=False):
    if order not in ('C', 'F', 'A', 'K'):
        raise ValueError('order must be C, F, A, or K')
    if _supported(a) and (a.ndim == 1 or order != 'F'):
        return a.copy()
    return np.copy(_convert(a), order=order, subok=subok)


def _count_nonzero(a, axis=None, *, keepdims=False):
    if axis is None and _supported(a):
        count = a.size - a.count(0)
        return np.full((1,) * a.ndim, count, dtype=np.intp) if keepdims else count
    return np.count_nonzero(_convert(a), axis=axis, keepdims=keepdims)


def _take(a, indices, axis=None, out=None, mode='raise'):
    if _supported(out):
        return NotImplemented
    if isinstance(a, Array) and axis in (None, 0, -1) and out is None and mode == 'raise':
        idx = np.asarray(indices)
        if idx.ndim == 1 and idx.dtype == np.dtype(np.intp):
            return a.gather(idx)
    return np.take(_convert(a), _convert(indices), axis=axis, out=out, mode=mode)


_HANDLERS = {np.array_equal: _array_equal, np.copy: _copy,
             np.count_nonzero: _count_nonzero, np.take: _take}
_FALLBACKS = {np.sum, np.prod, np.mean, np.min, np.max, np.all, np.any,
              np.concatenate, np.stack, np.reshape, np.transpose}


def array_function(self, function, types, args, kwargs):
    from . import Matrix
    if not all(t in (Array, Matrix, np.ndarray) for t in types):
        return NotImplemented
    if function in _HANDLERS:
        return _HANDLERS[function](*args, **kwargs)
    if function in _FALLBACKS:
        out_positions = {np.sum: 3, np.prod: 3, np.mean: 3, np.min: 2, np.max: 2,
                         np.all: 2, np.any: 2, np.concatenate: 2, np.stack: 3}
        at = out_positions.get(function, len(args))
        if _supported(kwargs.get('out')) or (len(args) > at and _supported(args[at])):
            return NotImplemented
        return function(*_convert(args), **_convert(kwargs))
    return NotImplemented
