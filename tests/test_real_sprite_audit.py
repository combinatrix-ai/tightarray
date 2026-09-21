import pytest

pytest.importorskip("pygame")
pytest.importorskip("PIL")
from benchmarks.real_sprite_audit import audit


def test_real_asset_roundtrip():
    result = audit()  # audit asserts byte-exact RGBA roundtrip for each asset
    assert len(result["records"]) == 10
    for row in result["records"]:
        assert 1 <= row["bits"] <= 8
        assert row["colors"] <= 2 ** row["bits"]
        assert row["packed_palette_bytes"] <= row["uint8_palette_bytes"] + 7
