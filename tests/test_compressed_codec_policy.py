import pytest

pytest.importorskip("blosc2")
pytest.importorskip("numpy")

from benchmarks.compressed_codec_policy import decode, encode, extras
from tightarray.compressed import CompressedArray


@pytest.mark.parametrize("codec", ["lz4", "zstd"])
def test_policies_roundtrip_small_patterns(codec):
    store = CompressedArray([], codec=codec)
    patterns = [
        b"\xff" * 256,
        bytes(range(8)) * 32,
        bytes([200, 249]) * 128,
        bytes(255) + b"\xff",
    ]
    for raw in patterns:
        for policy in (
            "exhaustive",
            "best-only",
            "raw-only",
            "stats-once",
            "entropy-skip",
            "best+raw",
            "probe-smallest",
        ):
            result, calls = encode(raw, store, policy)
            assert decode(result, len(raw), store) == raw
            assert calls >= 0


def test_phase_preserves_dataset_stream_and_names():
    main = list(extras(256, 64, False))
    followup = list(extras(256, 64, True))
    assert len(main) == 6
    assert len(followup) == 8
    assert [name for name, _ in main] == [name for name, _ in followup[2:]]
    assert main[0][1].tobytes() == followup[2][1].tobytes()
    # Additional random draws intentionally change later adverse cases.
    assert main[2][1].tobytes() != followup[4][1].tobytes()
