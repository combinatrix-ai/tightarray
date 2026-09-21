import sys

import pytest

pytest.importorskip("blosc2")

import tightarray.compressed as live
from benchmarks.compressed_trimmed_policy import retained_graph_bytes
from tightarray import Array


def test_span_retained_graph_includes_owned_references():
    data = Array(bytes([0, 1]) * 100, bits=1)
    palette = bytes([3, 200])
    span = live._native._SpanHot(data, palette, default=0, start=100, length=500)
    expected = sys.getsizeof(span) + sys.getsizeof(data) + sys.getsizeof(palette)
    assert retained_graph_bytes(span) == expected
    assert (
        retained_graph_bytes([span, data, palette])
        == sys.getsizeof([span, data, palette]) + expected
    )


def test_integrated_small_run_checks_all_cases():
    from benchmarks.compressed_trimmed_integrated import run

    result = run(size=4096, repeats=1)
    assert len(result["records"]) == 9
    assert all(len(row["samples"]) == 6 for row in result["records"])
