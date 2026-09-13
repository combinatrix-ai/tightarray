"""Enable the five upstream remainder checks, without editing the pinned suite."""
import pytest


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items):
    for item in items:
        if (item.path.name == 'test_operators_and_elementwise_functions.py'
                and item.originalname == 'test_remainder'):
            item.own_markers[:] = [
                mark for mark in item.own_markers
                if not (mark.name == 'skip' and mark.kwargs.get('reason') == 'flaky')
            ]
