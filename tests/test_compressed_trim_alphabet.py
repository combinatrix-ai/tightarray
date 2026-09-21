"""Smoke coverage for isolated planner/encode measurement records."""

import json

import pytest

from benchmarks import compressed_trim_alphabet as bench


def test_worker_records_all_phases(tmp_path, monkeypatch):
    pytest.importorskip("blosc2")
    raw = bytes(32) + bytes(range(1, 16)) * 2 + bytes(32)
    monkeypatch.setattr(bench, "cases", lambda: [("sample", raw)])
    target = tmp_path / "worker.json"
    bench.worker(target, 2, 3)
    result = json.loads(target.read_text())
    assert len(result["rows"]) == 8
    assert {r["kind"] for r in result["rows"]} == {"planner", "none", "lz4", "zstd"}
    assert all(len(r["ns"]) == 2 and r["median_ns"] > 0 for r in result["rows"])
    assert result["sources"]
