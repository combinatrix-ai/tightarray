"""Check saved output digests and the independent upstream Scirpy fixture."""
import json
import os
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import load_npz

from adapters import hamming

results = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / 'results'
for project in ('bionumpy', 'immuneml', 'motifboost', 'scirpy', 'deeprc', 'compairr', 'motifboost_ingest'):
    paths = sorted(results.glob(project + '-*.json'))
    records = [json.loads(path.read_text()) for path in paths if path.name != 'scirpy-compiled.json']
    assert {'baseline', 'candidate'} <= {r['backend'] for r in records}, project
    assert len({r['digest'] for r in records}) == 1, project
    print(project, 'matching digests:', len(records))
fixture = Path(os.environ['BIO_PILOT_ROOT']) / 'repos/scirpy/src/scirpy/tests/data/hamming_test_data'
actual = hamming(np.load(fixture / 'hamming_WU3k_seqs.npy', allow_pickle=False).tolist(), 2)
expected = load_npz(fixture / 'hamming_WU3k_csr_result.npz')
assert actual.shape == expected.shape and (actual != expected).nnz == 0
print('Scirpy independent fixture matches:', actual.shape, actual.nnz)
