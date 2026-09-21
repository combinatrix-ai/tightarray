import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_header_pruning import run


def test_header_prune_small_matrix_and_call_counts():
    result = run(size=4096, repeats=1)
    assert len(result["records"]) == 16
    for row in result["records"]:
        assert len(row["samples"]) == 6
        assert row["compress_calls"]["native-none"]["construction"] == 0
        for codec in ("lz4", "zstd"):
            for phase in ("construction", "updates_flush"):
                assert (
                    row["compress_calls"][f"native-{codec}"][phase]
                    <= row["compress_calls"][f"base-{codec}"][phase]
                )
    tiny = next(r for r in result["records"] if r["case"] == "two-period-direct")
    assert tiny["compress_calls"]["base-zstd"]["construction"] > 0
    assert tiny["compress_calls"]["native-zstd"]["construction"] == 0
