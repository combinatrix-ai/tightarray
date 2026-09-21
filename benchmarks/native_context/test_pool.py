"""Optional native-pool phase correctness; requires disposable extension."""

import pytest

pytest.importorskip("ta_ccontext")

from benchmarks import compressed_context_phases as phases
from benchmarks.compressed_ccontext_study import NativePool, pool_factory
from benchmarks.compressed_hot_bulk import cases, make_trace
from benchmarks.compressed_shared_context import independent_compress


@pytest.mark.parametrize("codec", ["lz4", "zstd"])
def test_native_pool_output_ownership(codec):
    pool = NativePool(max_contexts=2)
    held = []
    for shuffle in (False, True):
        for value in (0, 3, 200, 17):
            raw = bytes([value]) * 4096
            expected = independent_compress(codec, raw, shuffle)
            result = pool.compress(codec, raw, shuffle)
            assert result == expected
            held.append((result, expected))
    assert pool.info()["idle_retained_chunk_bytes"] == 0
    pool.clear()
    assert all(a == b for a, b in held)


@pytest.mark.parametrize("budget", [512, 65536])
def test_phase_exact(budget):
    data, labels = cases()["direct-5bit"]
    writes, expected, _ = make_trace(data, labels, 16, count=3)
    baseline = phases.trial(data, budget, "zstd", "adaptive", writes, expected)
    with pool_factory(phases, NativePool):
        for mode in ("shared-cold", "shared-warm"):
            row = phases.trial(data, budget, "zstd", mode, writes, expected)
            assert row["cold_sha256"] == baseline["cold_sha256"]
            assert row["pool_after"]["idle_retained_chunk_bytes"] == 0
