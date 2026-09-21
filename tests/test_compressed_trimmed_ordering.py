import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_trimmed_ordering import run


def test_native_ordering_small_run():
    result = run(size=4096, repeats=1)
    assert len(result["records"]) == 9
    assert all(len(row["samples"]) == 7 for row in result["records"])
