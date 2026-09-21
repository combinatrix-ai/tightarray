import pytest

pytest.importorskip("blosc2")

import tightarray.compressed as live
from benchmarks.compressed_span_bulk import cases, trace, trial
from benchmarks.compressed_trimmed_policy import pinned_baseline


@pytest.mark.parametrize(
    "case", ["direct-3bit", "direct-5bit", "palette-3bit", "palette-5bit"]
)
@pytest.mark.parametrize("budget", [0, 512, 65536])
def test_bulk_benchmark_reloads_all_changed_values(case, budget):
    data, labels = cases()[case]
    with pinned_baseline("6a3ffb2") as (base, _):
        for region in ("inside", "outside", "mixed"):
            writes, expected, count = trace(data, labels, region)
            assert count == 512
            for cls in (base, live.CompressedArray):
                result = trial(cls, "palette-none", data, budget, writes, expected)
                assert result["after"]["cache_bytes"] <= budget
            trial(live.CompressedArray, "dense-zstd", data, budget, writes, expected)
