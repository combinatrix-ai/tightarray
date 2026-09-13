"""Compare the packaged adapter with pinned upstream; all imports/setup excluded."""

import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from tightarray_immune import AMINO_ACIDS
from tightarray_immune.motifboost import MotifRepertoire, ngram_features

root = Path(os.environ["BIO_PILOT_ROOT"])
sys.path.insert(0, str(root / "repos/MotifBoost"))
from motifboost.methods.motif import ngram_features as original
from motifboost.sequences import PackedStringArray

path = (
    root / "repos/scirpy/src/scirpy/tests/data/hamming_test_data/hamming_WU3k_seqs.npy"
)
seqs = np.load(path, allow_pickle=False).tolist()
weights = np.arange(len(seqs), dtype=np.int64) % 5 + 1
resident = MotifRepertoire(seqs)
packed = PackedStringArray(list(AMINO_ACIDS))
packed.bulk_append(seqs)
functions = {
    "original_strings": lambda: original(seqs, count_weights=weights),
    "adapter_strings": lambda: ngram_features(seqs, weights),
    "original_resident": lambda: original(packed.get_all_strs(), count_weights=weights),
    "adapter_resident": lambda: resident.features(weights),
}
expected = original(seqs, count_weights=weights)
for fn in functions.values():
    np.testing.assert_array_equal(fn(), expected)
samples = {name: [] for name in functions}
for trial in range(10):
    for name in list(functions)[:: 1 if trial % 2 == 0 else -1]:
        start = time.perf_counter()
        actual = functions[name]()
        elapsed = time.perf_counter() - start
        np.testing.assert_array_equal(actual, expected)
        samples[name].append(elapsed)
result = {
    "scope": "weighted normalized trigrams, no training; encoding included in strings paths",
    "sequences": len(seqs),
    "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    "output_sha256": hashlib.sha256(expected.tobytes()).hexdigest(),
    "median_s": {name: statistics.median(values) for name, values in samples.items()},
    "samples_s": samples,
    "retained_payload_bytes": {
        "original": len(packed.data.tobytes()) + packed.indices.nbytes,
        "adapter": resident.nbytes,
    },
    "method": "one warmup, ten samples, alternate execution order; same process",
}
Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
