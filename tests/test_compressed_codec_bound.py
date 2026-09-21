"""Prune only encodings provably smaller than a codec's minimum header."""

import pytest

from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("codec", ["lz4", "zstd"])
@pytest.mark.parametrize(
    "raw",
    [
        bytes([0, 1]) * 2048,
        bytes([200, 201]) * 2048,
        bytes(2000) + b"\xff" + bytes(2095),
    ],
)
def test_small_structural_record_avoids_codec_calls(monkeypatch, codec, raw):
    blosc = pytest.importorskip("blosc2")
    baseline = CompressedArray(raw, codec="none")
    assert baseline.storage_info().stored_bytes < blosc.MIN_HEADER_LENGTH

    def fail(self, raw, *, shuffle):
        raise AssertionError("codec cannot beat this record")

    monkeypatch.setattr(CompressedArray, "_compress", fail)
    array = CompressedArray(raw, codec=codec)
    assert array._chunks == baseline._chunks
    assert array.tobytes() == raw


def test_equal_header_bound_preserves_codec_tie(monkeypatch):
    blosc = pytest.importorskip("blosc2")
    minimum = blosc.MIN_HEADER_LENGTH
    assert 4 <= minimum <= 512 and minimum % 2 == 0
    raw = b"".join(bytes([value]) * 32 for value in range(minimum // 2))
    array = CompressedArray(raw, chunk_size=len(raw), palette=False)
    assert array.storage_info().stored_bytes == minimum
    calls = []

    def fake(self, raw, *, shuffle):
        calls.append(len(raw))
        return bytes(minimum)

    monkeypatch.setattr(CompressedArray, "_compress", fake)
    encoded = CompressedArray(raw, chunk_size=len(raw), codec="zstd", palette=False)
    assert calls
    assert encoded.storage_info().compressed_chunks == 1
    assert encoded.storage_info().rle_chunks == 0
    # Synthetic payload tests selection only; it is not a decodable Blosc frame.


def test_palette_lower_bound_uses_best_encoded_record(monkeypatch):
    blosc = pytest.importorskip("blosc2")
    calls = []

    def fake(self, raw, *, shuffle):
        calls.append(shuffle)
        return bytes(blosc.MIN_HEADER_LENGTH)

    monkeypatch.setattr(CompressedArray, "_compress", fake)
    raw = bytes(range(128, 192)) * 64
    array = CompressedArray(raw, codec="zstd")
    # Zero-palette equality still competes, but a 64-byte palette cannot win.
    assert calls == [False, True]
    assert array.storage_info().compressed_chunks == 1
    assert array.storage_info().palette_chunks == 0
