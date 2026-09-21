"""Shared context trial retains exact records across cold and warm paths."""

import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_context_phases import trial
from benchmarks.compressed_hot_bulk import cases, make_trace


@pytest.mark.parametrize("budget", [512, 65536])
@pytest.mark.parametrize("codec", ["lz4", "zstd"])
def test_pool_phases_exact(budget, codec):
    data, labels = cases()["direct-3bit"]
    writes, expected, _ = make_trace(data, labels, 16, count=3)
    rows = [
        trial(data, budget, codec, mode, writes, expected)
        for mode in ("adaptive", "shared-cold", "shared-warm")
    ]
    assert len({row["cold_sha256"] for row in rows}) == 1
    assert rows[1]["pool_before"]["contexts"] == 0
    assert rows[2]["pool_before"]["contexts"] > 0
    assert all(row["total_ms"] >= row["updates_ms"] for row in rows)
