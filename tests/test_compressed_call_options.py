"""Check byte-identical codec calls across wrapper/argument policies."""

import pytest

blosc2 = pytest.importorskip("blosc2")

from benchmarks.compressed_call_options import compress, datasets, source_guards


@pytest.mark.parametrize("codec", [blosc2.Codec.LZ4, blosc2.Codec.ZSTD])
@pytest.mark.parametrize("shuffle", [False, True])
def test_call_policies_are_exact(codec, shuffle):
    for _, raw in datasets():
        expected = compress(raw, codec, shuffle, "public-list")
        for policy in ("public-tuple", "extension-list", "extension-tuple"):
            actual = compress(raw, codec, shuffle, policy)
            assert actual == expected
            assert blosc2.decompress2(actual, nthreads=1) == raw


def test_guards_cover_wrapper_and_extension():
    paths = source_guards()
    assert any(path.endswith("/blosc2/core.py") for path in paths)
    assert str(blosc2.blosc2_ext.__file__) in paths
