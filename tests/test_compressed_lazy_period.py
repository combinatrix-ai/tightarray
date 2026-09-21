"""No-history lazy period oracle uses current compatible encoder source."""

from pathlib import Path

import tightarray.compressed as live
from benchmarks.compressed_input_dispatch import modules
from benchmarks.compressed_lazy_period import cases, policies_for
from benchmarks.compressed_period_after_rle import eager_source


def test_lazy_period_preserves_cold_records_without_codecs():
    source = eager_source(Path(live.__file__).read_text())
    with modules(policies_for(source, winner_size="winner_size")) as policies:
        inputs = list(cases().values())
        inputs += [raw[:-1] for raw in inputs if len(raw) > 512]
        for raw in inputs:
            for palette in (False, True):
                arrays = [
                    m.CompressedArray(raw, chunk_size=len(raw), palette=palette)
                    for m in policies.values()
                ]
                assert all(arr._chunks == arrays[0]._chunks for arr in arrays)
                assert all(arr.tobytes() == raw for arr in arrays)
