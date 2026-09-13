"""Context-local policy for implicit packed storage widening."""
from contextlib import contextmanager
from contextvars import ContextVar
import warnings
from typing import Iterator


class StorageWideningWarning(UserWarning):
    """Assignment requires repacking the shared root at a larger bit width."""


class StorageWideningError(ValueError):
    """Strict mode rejected implicit storage widening before mutation."""


_strict = ContextVar('tightarray_storage_strict', default=False)


def set_strict(enabled: bool = True) -> None:
    """Set implicit-widening rejection in the current execution context."""
    if not isinstance(enabled, bool):
        raise TypeError('enabled must be a bool')
    _strict.set(enabled)


@contextmanager
def strict(enabled: bool = True) -> Iterator[None]:
    """Temporarily set widening policy; restore it even when the body raises."""
    if not isinstance(enabled, bool):
        raise TypeError('enabled must be a bool')
    token = _strict.set(enabled)
    try:
        yield
    finally:
        _strict.reset(token)


def _check_widen(old: int, new: int, size: int) -> None:
    message = (f'shared root storage widens from {old} to {new} bits '
               f'({size} elements); all shared views are affected')
    if _strict.get():
        raise StorageWideningError(message)
    warnings.warn(message, StorageWideningWarning, stacklevel=2)
