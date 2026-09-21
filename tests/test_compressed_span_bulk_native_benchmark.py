import pytest

pytest.importorskip("blosc2")

import tightarray.compressed as live
from benchmarks.compressed_span_bulk_native import BASELINE, common, sized_trace
from benchmarks.compressed_trimmed_policy import pinned_baseline


@pytest.mark.parametrize("width", [1, 16, 64, 256])
@pytest.mark.parametrize(
    "case", ["direct-3bit", "direct-5bit", "palette-3bit", "palette-5bit"]
)
def test_native_bulk_sized_trace_reloads(width, case):
    data, labels = common.cases()[case]
    writes, expected, changed = sized_trace(data, labels, width, count=8)
    assert changed == 8 * width
    with pinned_baseline(BASELINE) as (base, _):
        for cls in (base, live.CompressedArray):
            common.trial(cls, "palette-none", data, 512, writes, expected)
