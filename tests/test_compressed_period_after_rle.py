"""After-RLE period prototype: current compatible source, no Git history needed."""

from pathlib import Path

import pytest

import tightarray.compressed as live
from benchmarks.compressed_input_dispatch import modules
from benchmarks.compressed_lazy_period import cases, instrument
from benchmarks.compressed_period_after_rle import eager_source, policies_for


@pytest.mark.parametrize("codec", ["none", "lz4", "zstd"])
def test_period_after_rle_exact_records_and_partial_tails(codec):
    if codec != "none":
        pytest.importorskip("blosc2")
    current = Path(live.__file__).read_text()
    source = eager_source(current)
    inputs = list(cases().values())
    inputs += [raw[:-1] for raw in inputs if len(raw) > 512]
    variants = policies_for(source)
    variants["current-unchanged"] = current
    with modules(variants) as policies:
        for raw in inputs:
            for palette in (False, True):
                arrays = []
                traces = []
                for module in policies.values():
                    traced = instrument(module.CompressedArray)
                    traced.calls = []
                    arr = traced(raw, chunk_size=len(raw), palette=palette, codec=codec)
                    arrays.append(arr)
                    traces.append(traced.calls)
                assert all(a._chunks == arrays[0]._chunks for a in arrays)
                assert all(a.tobytes() == raw for a in arrays)
                assert all(trace == traces[0] for trace in traces)


def test_eager_normalization_roundtrip_preserves_source_semantics():
    import ast

    from benchmarks.compressed_period_after_rle import after_rle_source

    current = Path(live.__file__).read_text()
    eager = eager_source(current)
    assert eager_source(eager) == eager
    restored = eager_source(after_rle_source(eager, True))
    assert ast.dump(ast.parse(restored)) == ast.dump(ast.parse(eager))
