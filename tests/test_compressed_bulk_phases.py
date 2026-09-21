import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_bulk_phases import cases, instrument, make_trace, trial


@pytest.mark.parametrize("budget", [512, 65536])
@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
def test_phase_counts_and_content(budget, codec):
    data, labels = cases()["direct-5bit"]
    writes, expected, changes = make_trace(data, labels, 16, count=4)
    assert changes == 64
    for dense in [False] if codec == "none" else [False, True]:
        measured = trial(data, budget, codec, dense, writes, expected)
        assert measured["updates_ms"] + measured["flush_ms"] == pytest.approx(
            measured["total_ms"]
        )
        counts = instrument(data, budget, codec, dense, writes, expected)
        if budget == 65536:
            assert counts["updates"]["encode_calls"] == 0
            assert counts["flush"]["encode_calls"] == 1
        else:
            assert counts["updates"]["encode_calls"] == 4
            assert counts["flush"]["encode_calls"] == 0
