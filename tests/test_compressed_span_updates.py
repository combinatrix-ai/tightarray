import pytest

pytest.importorskip("blosc2")

import tightarray.compressed as live
from benchmarks.compressed_span_updates import cases, trace, trial
from benchmarks.compressed_trimmed_policy import pinned_baseline


@pytest.mark.parametrize("budget", [0, 512, 65536])
@pytest.mark.parametrize("region", ["inside", "outside", "mixed"])
def test_changed_span_writes_survive_flush_reload(budget, region):
    data = cases()["span512"]
    writes, expected = trace(data, region)
    assert all(int(data[i]) != value for i, value in writes)
    with pinned_baseline("5defad8") as (base, _):
        for cls in (base, live.CompressedArray):
            result = trial(cls, "palette-none", data, budget, writes, expected)
            assert result["after"]["cache_bytes"] <= budget
