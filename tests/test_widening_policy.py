import contextvars
import warnings
import numpy as np
import pytest
from tightarray import Array
from tightarray import array_api as xp


def sample():
    return xp.reshape(xp.asarray(Array([1, 2, 3, 4], bits=3)), (2, 2))


@pytest.mark.parametrize('kind', ['scalar', 'slice', 'advanced'])
def test_warning_and_atomic_rejection(kind):
    x = sample()
    view = x[::-1]
    key = {'scalar': (0, 0), 'slice': (slice(None), 0),
           'advanced': (np.array([0, 1]), 0)}[kind]
    original = np.asarray(x).copy()
    for mode in ['strict', 'warning-error']:
        with warnings.catch_warnings(), xp.strict(mode == 'strict'):
            warnings.simplefilter('error', xp.StorageWideningWarning)
            error = xp.StorageWideningError if mode == 'strict' else xp.StorageWideningWarning
            with pytest.raises(error):
                view[key] = 31
        assert x.storage_bits == view.storage_bits == 3
        np.testing.assert_array_equal(np.asarray(x), original)
    with pytest.warns(xp.StorageWideningWarning, match='3 to 5 bits'):
        view[key] = 31
    assert x.storage_bits == view.storage_bits == 5
    assert x.dtype == xp.uint8
    with warnings.catch_warnings():
        warnings.simplefilter('error', xp.StorageWideningWarning)
        view[key] = 30  # No widening, no warning.


def test_context_restoration_and_isolation():
    xp.set_strict(True)
    try:
        assert contextvars.Context().run(lambda: _can_widen())
        with xp.strict(False), pytest.warns(xp.StorageWideningWarning):
            sample()[0, 0] = 31
        with pytest.raises(RuntimeError):
            with xp.strict(False):
                raise RuntimeError()
        with pytest.raises(xp.StorageWideningError):
            sample()[0, 0] = 31
    finally:
        xp.set_strict(False)


def _can_widen():
    with pytest.warns(xp.StorageWideningWarning):
        sample()[0, 0] = 31
    return True


@pytest.mark.parametrize('value', [1, None, 'yes'])
def test_policy_requires_boolean(value):
    with pytest.raises(TypeError):
        xp.set_strict(value)
    with pytest.raises(TypeError):
        with xp.strict(value):
            pass
