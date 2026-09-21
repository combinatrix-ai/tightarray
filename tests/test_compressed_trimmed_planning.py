import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_trimmed_planning import run


def test_small_planner_ablation_validates_all_variants():
    result = run(size=4096, repeats=1)
    assert len(result["records"]) == 9
    assert all(len(row["samples"]) == 9 for row in result["records"])
    assert set(result["baseline_commits"]) == {"pretrim", "early", "late"}
