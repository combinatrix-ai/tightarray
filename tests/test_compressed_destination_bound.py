import pytest

pytest.importorskip("blosc2")

from benchmarks.compressed_destination_bound import NO_FIT, limited


def test_only_exact_no_fit_error_is_accepted():
    class Fake:
        def __init__(self, message):
            self.message = message

        def _prefilter_data(self, index, raw, dst):
            raise RuntimeError(self.message)

    assert limited(Fake(NO_FIT), b"data", 10)[0]["status"] == "no-fit"
    assert (
        limited(Fake("Could not compress the data"), b"data", 10)[0]["status"]
        == "unexpected-error"
    )


def test_mutable_bounded_destination_and_copy():
    class Fake:
        def _prefilter_data(self, index, raw, dst):
            assert not dst.readonly and len(dst) == 3
            dst[:] = b"abc"
            self.saved = dst
            return 3

    fake = Fake()
    result, payload = limited(fake, b"source", 3)
    fake.saved[0] = 0
    assert result == {"status": "ok", "size": 3}
    assert payload == b"abc"


def test_pinned_zstd_exact_destination_counterexample():
    import blosc2

    from benchmarks.compressed_destination_bound import check_candidate

    if blosc2.__version__ != "4.13.1":
        pytest.skip("Historical counterexample is pinned to Blosc2 4.13.1")
    raw = bytes(17) + b"\xff" + bytes(46)
    result = check_candidate(raw, "zstd", False, 8)
    assert result["full_equal"] and result["post_limits_full_equal"]
    assert result["baseline_length"] == 61 < len(raw)
    equal = next(t for t in result["trials"] if t["label"] == "size-equal")
    extra = next(t for t in result["trials"] if t["label"] == "size-plus-one")
    assert equal["false_negative"] and extra["false_negative"]
    assert equal["status"] == extra["status"] == "no-fit"
