import pytest

from benchmarks.compressed_memcpy import native_trial


@pytest.mark.parametrize("layout", ["packed", "word-aligned"])
@pytest.mark.parametrize("offset", [0, 7])
@pytest.mark.parametrize("width", [1, 16, 64, 256, 4096])
def test_native_copy_benchmark_views_preserve_neighbors(layout, offset, width):
    result = native_trial(8, False, layout, offset, width, count=3)
    assert result["changes"] == 3 * width


@pytest.mark.parametrize("bits,palette", [(3, False), (5, False), (3, True), (5, True)])
def test_copy_benchmark_control_patterns(bits, palette):
    result = native_trial(bits, palette, "packed", 7, 64, count=3)
    assert result["changes"] == 192
