import pytest

pytest.importorskip("blosc2")

import tightarray.compressed as live
from benchmarks.compressed_hot_bulk import (
    BASELINE,
    cases,
    configurations,
    make_trace,
    trial,
)
from benchmarks.compressed_trimmed_policy import pinned_baseline


@pytest.mark.parametrize(
    "case",
    [
        "direct-3bit",
        "direct-5bit",
        "direct-8bit",
        "palette-3bit",
        "palette-5bit",
        "periodic-control",
        "span-control",
    ],
)
def test_hot_bulk_benchmark_changed_values_and_cold_equality(case):
    data, labels = cases()[case]
    with pinned_baseline(BASELINE) as (base, _):
        for width in (1, 16, 64, 256, 4096):
            writes, expected, count = make_trace(data, labels, width, count=2)
            assert count == width * 2
            old = trial(base, "palette-none", data, 65536, writes, expected)
            new = trial(
                live.CompressedArray, "palette-none", data, 65536, writes, expected
            )
            assert old["cold_sha256"] == new["cold_sha256"]


def test_hot_bulk_shrink_and_eviction_traces():
    for name, data, budget, width, writes, expected, changes in configurations():
        if name in ("remove-only-max", "eviction-direct3"):
            trial(live.CompressedArray, "palette-none", data, budget, writes, expected)
