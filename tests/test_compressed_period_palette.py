import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_period_palette import run


def test_period_palette_small_matrix():
    # At least16 tiny10-byte chunks keep the shared64-byte read trace valid.
    result = run(size=65536, repeats=1)
    assert len(result["records"]) == 7
    assert all(len(row["samples"]) == 6 for row in result["records"])
    expected = {
        "high32-period32": 33,
        "high-two-period2": 9,
        "high-two-period31": 11,
        "tiny-high-period2": 9,
    }
    for row in result["records"]:
        if row["case"] in expected:
            info = row["samples"]["live-none"][0]["initial_storage"]
            assert info["stored_bytes"] == 16 * expected[row["case"]]
