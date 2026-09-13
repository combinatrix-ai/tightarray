"""Array API 2025.12 namespace with packed uint8/bool and NumPy numerical kernels.

Native Array/Matrix remain the low-overhead API. This namespace supplies the
standard's scalar/ND object semantics; other dtypes use NumPy storage.
"""
from __future__ import annotations

import builtins as _builtins
import functools as _functools
import math as _math
import operator as _operator
import numpy as _np
from .._core import Array as _NativeArray

__array_api_version__ = '2025.12'
__version__ = '0.1.0.dev0'

for _name in ('bool', 'uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16', 'int32', 'int64',
              'float32', 'float64', 'complex64', 'complex128'):
    globals()[_name] = getattr(_np, _name)
e, pi, inf, nan = _np.e, _np.pi, _np.inf, _np.nan
newaxis = None


def _strides(shape):
    out, step = [], 1
    for n in reversed(shape):
        out.append(step)
        step *= n
    return tuple(reversed(out))


class _Storage:
    __slots__ = ('data',)

    def __init__(self, data):
        self.data = data


class Array:
    """Standard array object; uint8/bool views share a native packed allocation."""
    __slots__ = ('_storage', '_shape', '_strides', '_offset', '_dtype', '_numpy')
    __hash__ = None

    @classmethod
    def _from_numpy(cls, value):
        obj = cls.__new__(cls)
        a = _np.asarray(value)
        obj._shape, obj._dtype = a.shape, a.dtype
        obj._offset, obj._strides, obj._storage = 0, _strides(a.shape), None
        if a.dtype in (uint8, bool):
            values = a.ravel().astype(_np.uint8, copy=False)
            bits = 1 if a.dtype == bool or not a.size else _builtins.max(1, _builtins.int(values.max()).bit_length())
            obj._storage = _Storage(_NativeArray(values, bits=bits))
            obj._numpy = None
        else:
            obj._numpy = a
        return obj

    def _view(self, shape, strides, offset):
        obj = type(self).__new__(type(self))
        obj._storage, obj._dtype, obj._numpy = self._storage, self._dtype, None
        obj._shape, obj._strides, obj._offset = shape, strides, offset
        return obj

    @property
    def shape(self):
        return self._shape

    @property
    def ndim(self):
        return len(self.shape)

    @property
    def size(self):
        return _math.prod(self.shape)

    @property
    def dtype(self):
        return self._dtype

    @property
    def device(self):
        return 'cpu'

    @property
    def storage_bits(self):
        return self._storage.data.bits if self._storage else self.dtype.itemsize * 8

    @property
    def storage_nbytes(self):
        return self._storage.data.nbytes if self._storage else self._numpy.nbytes

    @property
    def T(self):
        if self.ndim != 2:
            raise ValueError('T requires a two-dimensional array')
        return permute_dims(self, (1, 0))

    @property
    def mT(self):
        if self.ndim < 2:
            raise ValueError('mT requires at least two dimensions')
        axes = list(range(self.ndim))
        axes[-2:] = axes[-2:][::-1]
        return permute_dims(self, tuple(axes))

    def _unpack(self):
        if self._storage is None:
            return self._numpy
        raw = self._storage.data._view_bytes(self.shape, self._strides, self._offset)
        return _np.frombuffer(raw, dtype=self.dtype).reshape(self.shape)

    def __array__(self, dtype=None, copy=None):
        if copy is False and (self._storage is not None or (dtype is not None and _np.dtype(dtype) != self.dtype)):
            raise ValueError('a copy is required')
        a = self._unpack()
        if dtype is not None:
            a = a.astype(dtype, copy=False)
        return a.copy() if copy is True or self._storage is not None else a

    def __array_namespace__(self, *, api_version=None):
        if api_version not in (None, __array_api_version__):
            raise ValueError(f'unsupported Array API version: {api_version}')
        import sys
        return sys.modules[__name__]

    def __dlpack_device__(self):
        return (1, 0)

    def __dlpack__(self, *, stream=None, max_version=None, dl_device=None, copy=None):
        if copy is False and self._storage is not None:
            raise BufferError('packed storage requires a copy for DLPack')
        a = self._unpack()
        exported_copy = True if self._storage is not None else copy
        return a.__dlpack__(stream=stream, max_version=max_version, dl_device=dl_device, copy=exported_copy)

    def to_device(self, device, /, *, stream=None):
        _device(device)
        if stream is not None:
            raise ValueError('CPU arrays do not accept a stream')
        return self

    def __len__(self):
        if not self.ndim:
            raise TypeError('len() of a scalar array')
        return self.shape[0]

    def _scalar(self, convert):
        if self.ndim:
            raise TypeError('scalar conversion requires a zero-dimensional array')
        if self._storage is not None:
            return convert(self.dtype.type(self._storage.data[self._offset]))
        return convert(self._numpy)

    def __bool__(self):
        return self._scalar(_builtins.bool)

    def __int__(self):
        return self._scalar(_builtins.int)

    def __float__(self):
        return self._scalar(_builtins.float)

    def __complex__(self):
        return self._scalar(_builtins.complex)

    def __index__(self):
        return self._scalar(_operator.index)

    def __repr__(self):
        return f'tightarray.array_api.Array({self._unpack()!r}, storage_bits={self.storage_bits})'

    def __getitem__(self, key):
        if self._storage is None:
            return _wrap(self._numpy[_unwrap(key)])
        if self.ndim == 1 and isinstance(key, (_builtins.int, _np.integer)) and not isinstance(key, (_builtins.bool, _np.bool_)):
            i = _operator.index(key)
            if i < 0: i += self.shape[0]
            if not 0 <= i < self.shape[0]: raise IndexError('index out of bounds')
            return self._view((), (), self._offset + i * self._strides[0])
        keys = key if isinstance(key, tuple) else (key,)
        basic = _builtins.all(k is None or k is Ellipsis or isinstance(k, (slice, _builtins.int, _np.integer)) and not isinstance(k, (_builtins.bool, _np.bool_)) for k in keys)
        if not basic:
            return _wrap(self._unpack()[_unwrap(key)])
        if _builtins.sum(k is Ellipsis for k in keys) > 1:
            raise IndexError('multiple ellipses')
        used = _builtins.sum(k is not None and k is not Ellipsis for k in keys)
        if used > self.ndim:
            raise IndexError('too many indices')
        expanded = []
        for k in keys:
            expanded.extend([slice(None)] * (self.ndim - used)) if k is Ellipsis else expanded.append(k)
        if not _builtins.any(k is Ellipsis for k in keys):
            expanded.extend([slice(None)] * (self.ndim - used))
        shape, strides, offset, axis = [], [], self._offset, 0
        for k in expanded:
            if k is None:
                shape.append(1); strides.append(0)
                continue
            n, stride = self.shape[axis], self._strides[axis]
            axis += 1
            if isinstance(k, slice):
                start, stop, step = k.indices(n)
                shape.append(len(range(start, stop, step)))
                strides.append(stride * step)
                offset += start * stride
            else:
                i = _operator.index(k)
                if i < 0:
                    i += n
                if not 0 <= i < n:
                    raise IndexError('index out of bounds')
                offset += i * stride
        return self._view(tuple(shape), tuple(strides), offset)

    def __setitem__(self, key, value):
        if self._storage is None:
            self._numpy[_unwrap(key)] = _unwrap(value)
            return
        target = self[key]
        if target._storage is self._storage:
            # Snapshot and cast before writing: overlapping views have NumPy semantics.
            values = _np.empty(target.shape, dtype=self.dtype)
            values[...] = _unwrap(value)
            target._assign_values(values)
        else:
            # Advanced indexing fallback; shared basic views take the direct path.
            values = self._unpack().copy()
            values[_unwrap(key)] = _unwrap(value)
            self._assign_values(values)

    def _assign_values(self, values):
        needed = 1 if self.dtype == bool or not values.size else _builtins.max(1, _builtins.int(values.max()).bit_length())
        if needed > self._storage.data.bits:
            old = self._storage.data
            self._storage.data = _NativeArray(old.tobytes(), bits=needed, layout=old.layout)
        if not self.ndim:
            self._storage.data[self._offset] = _builtins.int(values)
        else:
            self._storage.data._view_assign(self.shape, self._strides, self._offset, values.tobytes())


def _device(device):
    if device not in (None, 'cpu'):
        raise ValueError('only the cpu device is supported')


def _unwrap(value):
    if isinstance(value, Array):
        return value._unpack()
    if isinstance(value, tuple):
        return tuple(_unwrap(v) for v in value)
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    if isinstance(value, dict):
        return {k: _unwrap(v) for k, v in value.items()}
    return value


def _wrap(value):
    if isinstance(value, (_np.ndarray, _np.generic)):
        return Array._from_numpy(value)
    if isinstance(value, tuple):
        if hasattr(value, '_fields'):
            return type(value)(*(_wrap(v) for v in value))
        return tuple(_wrap(v) for v in value)
    if isinstance(value, list):
        return [_wrap(v) for v in value]
    return value


def asarray(obj, /, *, dtype=None, device=None, copy=None):
    _device(device)
    if isinstance(obj, Array):
        if dtype is None or _np.dtype(dtype) == obj.dtype:
            if copy is not True:
                return obj
        elif copy is False:
            raise ValueError('dtype conversion requires a copy')
        return _wrap(_np.asarray(obj._unpack(), dtype=dtype).copy())
    if isinstance(obj, _NativeArray) and (dtype is None or _np.dtype(dtype) == uint8):
        if copy is False:
            raise ValueError('adapting fixed-width native storage requires a copy')
        out = Array.__new__(Array)
        out._storage = _Storage(obj.copy())
        out._shape, out._strides, out._offset, out._dtype, out._numpy = (len(obj),), (1,), 0, _np.dtype(uint8), None
        return out
    if copy is False:
        raise ValueError('external conversion requires a copy')
    return _wrap(_np.array(_unwrap(obj), dtype=dtype, copy=copy))


def astype(x, dtype, /, *, copy=True, device=None):
    _device(device)
    target = _np.dtype(dtype)
    if not copy and target == x.dtype:
        return x
    if x.dtype.kind == 'c' and target.kind != 'c':
        raise TypeError('complex arrays cannot be cast to real-valued dtypes')
    return _wrap(x._unpack().astype(target, copy=copy))


def reshape(x, /, shape, *, copy=None):
    a = _np.reshape(x._unpack(), shape, copy=copy)
    if x._storage is None:
        return _wrap(a)
    if copy is False or (copy is None and x._strides == _strides(x.shape)):
        if x._strides != _strides(x.shape):
            raise ValueError('a copy is required')
        return x._view(a.shape, _strides(a.shape), x._offset)
    return _wrap(a)


def permute_dims(x, /, axes):
    if x._storage is None:
        return _wrap(_np.transpose(x._numpy, axes))
    axes = tuple(_operator.index(a) for a in axes)
    normalized = tuple(a + x.ndim if a < 0 else a for a in axes)
    if sorted(normalized) != list(range(x.ndim)):
        raise ValueError('axes must be a permutation')
    return x._view(tuple(x.shape[a] for a in normalized), tuple(x._strides[a] for a in normalized), x._offset)


def _function(name):
    fn = getattr(_np, name)
    @_functools.wraps(fn)
    def call(*args, **kwargs):
        return _wrap(fn(*_unwrap(args), **_unwrap(kwargs)))
    return call


# Only the standardized namespace is exported; NumPy-specific dispatch is separate.
_FUNCTIONS = '''abs acos add all any arange argmax argmin argsort asin asinh atan atan2
bitwise_and bitwise_invert bitwise_left_shift bitwise_or bitwise_right_shift bitwise_xor
broadcast_to can_cast ceil concat conj copysign cos cosh cumulative_sum
cumulative_prod divide empty empty_like equal exp expand_dims eye floor
full full_like greater greater_equal hypot imag isdtype isfinite isinf isnan less less_equal
linspace log log1p log2 log10 logaddexp logical_and logical_not logical_or logical_xor matmul
matrix_transpose max maximum mean min minimum multiply negative nonzero not_equal ones ones_like
positive pow prod real remainder repeat result_type roll round searchsorted sign signbit sin sinh
sort sqrt square squeeze stack std subtract sum take take_along_axis tan tensordot tril triu
trunc unstack var vecdot where zeros zeros_like unique_all unique_counts unique_inverse unique_values
count_nonzero diff flip moveaxis tile nextafter reciprocal isin broadcast_shapes'''.split()
for _name in _FUNCTIONS:
    if hasattr(_np, _name):
        globals()[_name] = _function(_name)


def _binary(name, reverse=False, inplace=False):
    def op(self, other):
        if not isinstance(other, (Array, _builtins.int, _builtins.float, _builtins.complex, _builtins.bool)):
            return NotImplemented
        result = globals()[name](other, self) if reverse else globals()[name](self, other)
        if inplace:
            if result.dtype != self.dtype or result.shape != self.shape:
                raise TypeError('in-place operations cannot change dtype or shape')
            self[...] = result
            return self
        return result
    return op


for _op, _fn in {'add': 'add', 'sub': 'subtract', 'mul': 'multiply', 'truediv': 'divide',
                 'floordiv': 'floor_divide', 'mod': 'remainder', 'pow': 'pow', 'matmul': 'matmul',
                 'and': 'bitwise_and', 'or': 'bitwise_or', 'xor': 'bitwise_xor',
                 'lshift': 'bitwise_left_shift', 'rshift': 'bitwise_right_shift',
                 'eq': 'equal', 'ne': 'not_equal', 'lt': 'less', 'le': 'less_equal',
                 'gt': 'greater', 'ge': 'greater_equal'}.items():
    setattr(Array, f'__{_op}__', _binary(_fn))
    if _op not in ('eq', 'ne', 'lt', 'le', 'gt', 'ge'):
        setattr(Array, f'__r{_op}__', _binary(_fn, reverse=True))
        setattr(Array, f'__i{_op}__', _binary(_fn, inplace=True))
for _op, _fn in {'neg': 'negative', 'pos': 'positive', 'abs': 'abs', 'invert': 'bitwise_invert'}.items():
    setattr(Array, f'__{_op}__', lambda self, name=_fn: globals()[name](self))


def finfo(type, /):
    from types import SimpleNamespace
    info = _np.finfo(type.dtype if isinstance(type, Array) else type)
    return SimpleNamespace(bits=info.bits, eps=_builtins.float(info.eps), max=_builtins.float(info.max),
                           min=_builtins.float(info.min), smallest_normal=_builtins.float(info.smallest_normal), dtype=info.dtype)


def iinfo(type, /):
    return _np.iinfo(type.dtype if isinstance(type, Array) else type)


def broadcast_arrays(*arrays):
    return tuple(_wrap(a) for a in _np.broadcast_arrays(*_unwrap(arrays)))


def meshgrid(*arrays, indexing='xy'):
    return tuple(_wrap(a) for a in _np.meshgrid(*_unwrap(arrays), indexing=indexing))


def from_dlpack(x, /, *, device=None, copy=None):
    _device(device)
    if isinstance(x, Array):
        return asarray(x, copy=copy)
    a = _np.from_dlpack(x, device=device, copy=copy)
    if copy is False and a.dtype in (uint8, bool):
        raise BufferError("packing external DLPack storage requires a copy")
    return _wrap(a)


def _extension(name):
    from types import ModuleType
    source = getattr(_np, name)
    module = ModuleType(__name__ + '.' + name)
    for key in dir(source):
        if not key.startswith('_') and callable(getattr(source, key)):
            fn = getattr(source, key)
            def call(*args, _fn=fn, **kwargs):
                return _wrap(_fn(*_unwrap(args), **_unwrap(kwargs)))
            _functools.update_wrapper(call, fn)
            setattr(module, key, call)
    return module


linalg = _extension('linalg')
fft = _extension('fft')

def __array_namespace_info__():
    from types import SimpleNamespace
    info = _np.__array_namespace_info__()
    return SimpleNamespace(capabilities=info.capabilities, devices=lambda: tuple(info.devices()),
                           default_device=info.default_device, default_dtypes=info.default_dtypes,
                           dtypes=info.dtypes)


def _fftfreq(n, /, *, d=1.0, dtype=None, device=None):
    _device(device)
    return _wrap(_np.fft.fftfreq(n, d=d).astype(dtype or float64, copy=False))


def _rfftfreq(n, /, *, d=1.0, dtype=None, device=None):
    _device(device)
    return _wrap(_np.fft.rfftfreq(n, d=d).astype(dtype or float64, copy=False))


fft.fftfreq = _fftfreq
fft.rfftfreq = _rfftfreq


def clip(x, /, min=None, max=None):
    return _wrap(_np.clip(_unwrap(x), min=_unwrap(min), max=_unwrap(max)))


def floor_divide(x1, x2, /):
    values = _unwrap((x1, x2))
    out = _np.asarray(_np.floor_divide(*values))
    if out.dtype.kind == 'f':
        a, b = _np.broadcast_arrays(*values)
        division = _np.asarray(a / b, dtype=out.dtype)
        out = _np.where((_np.isinf(a) & _np.isfinite(b) & (b != 0)) |
                        (_np.isfinite(a) & _np.isinf(b)), division, out)
    return _wrap(out)


def _complex_special(name, x):
    a = _unwrap(x)
    out = _np.asarray(getattr(_np, name)(a)).copy()
    if a.dtype.kind != 'c':
        return _wrap(out)
    r, i = a.real, a.imag
    if name == 'acosh':
        mask = (r == 0) & _np.isnan(i)
        out.real[...] = _np.where(mask, _np.nan, out.real)
        out.imag[...] = _np.where(mask, _np.pi / 2, out.imag)
    elif name == 'atanh':
        finite_nan = (_np.isfinite(r) & (r != 0) & _np.isnan(i)) | (_np.isnan(r) & _np.isfinite(i))
        out.real[...] = _np.where(finite_nan, _np.nan, out.real)
        out.imag[...] = _np.where(finite_nan, _np.nan, out.imag)
        zero_nan = (r == 0) & _np.isnan(i)
        pole = (_np.abs(r) == 1) & (i == 0)
        inf_nan = _np.isinf(r) & _np.isnan(i)
        nan_inf = _np.isnan(r) & _np.isinf(i)
        out.real[...] = _np.where(zero_nan, r, _np.where(pole, _np.copysign(_np.inf, r),
                            _np.where(inf_nan | nan_inf, _np.copysign(0.0, r), out.real)))
        out.imag[...] = _np.where(pole, i, _np.where(zero_nan | inf_nan, _np.nan,
                            _np.where(nan_inf, _np.copysign(_np.pi / 2, i), out.imag)))
    elif name == 'expm1':
        mask = ~_np.isfinite(r) | ~_np.isfinite(i)
        replacement = _np.exp(a) - 1
        out.real[...] = _np.where(mask, replacement.real, out.real)
        out.imag[...] = _np.where(mask, replacement.imag, out.imag)
        out.real[...] = _np.where((r == 0) & (i == 0), 0.0, out.real)
    elif name == 'tanh':
        zero_bad = (r == 0) & ~_np.isfinite(i)
        inf_finite = _np.isinf(r) & _np.isfinite(i)
        out.real[...] = _np.where(zero_bad, r, out.real)
        out.imag[...] = _np.where(zero_bad, _np.nan, _np.where(inf_finite, _np.copysign(0.0, i), out.imag))
    return _wrap(out)


def acosh(x, /):
    return _complex_special('acosh', x)


def atanh(x, /):
    return _complex_special('atanh', x)


def expm1(x, /):
    return _complex_special('expm1', x)


def tanh(x, /):
    return _complex_special('tanh', x)


def sum(x, /, *, axis=None, dtype=None, keepdims=False):
    if x._storage is not None and axis is None and (dtype is None or _np.dtype(dtype) == _np.dtype(uint64)):
        total = x._storage.data._view_sum(x.shape, x._strides, x._offset)
        out = _np.asarray(total, dtype=_np.int64 if dtype is None and x.dtype == bool else _np.uint64)
        if keepdims:
            out = out.reshape((1,) * x.ndim)
        return _wrap(out)
    return _wrap(_np.sum(_unwrap(x), axis=axis, dtype=dtype, keepdims=keepdims))
