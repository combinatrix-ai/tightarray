"""Measure the NumPy entry points separately from direct native methods."""
import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
from tightarray import Array
from run import deep_size, measure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = []
    for n in (65536, 1048576):
        for bits in (2, 5, 7):
            src = (np.arange(n, dtype=np.uint32) % (1 << bits)).astype(np.uint8)
            idx = np.linspace(0, n - 1, 256, dtype=np.intp)
            for name, a in [('numpy', src), ('packed', Array(src, bits=bits)),
                            ('word-aligned', Array(src, bits=bits, layout='word-aligned'))]:
                other = a.copy()
                operations = {'asarray': lambda: np.asarray(a),
                              'array_equal': lambda: np.array_equal(a, other),
                              'count_nonzero': lambda: np.count_nonzero(a),
                              'take': lambda: np.take(a, idx),
                              'add': lambda: np.add(a, 1)}
                expected = {'asarray': src, 'array_equal': True,
                            'count_nonzero': np.count_nonzero(src), 'take': src[idx], 'add': src + 1}
                for method, fn in operations.items():
                    np.testing.assert_array_equal(fn(), expected[method])
                    records.append(dict(elements=n, bits=bits, implementation=name,
                                        method=method, dataset_retained_bytes=deep_size(a),
                                        **measure(fn, 5, .005)))
            print(f'finished NumPy API bits={bits} n={n}', flush=True)
    root = Path(__file__).resolve().parents[1]
    sources = ['tightarray/_core.c', 'tightarray/_rows.h', 'tightarray/_numpy.h',
               'tightarray/_numpy.py', 'tightarray/__init__.py', 'benchmarks/run.py', 'benchmarks/run_numpy.py']
    metadata = dict(python=sys.version, numpy=np.__version__, platform=platform.platform(),
                    note='Public NumPy calls include dispatch and any unpacking; np.asarray(ndarray) may share data, while tightarray always copies. Deterministic periodic input; no isolation or cold-cache control.',
                    source_sha256={p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sources})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(metadata=metadata, results=records), indent=2) + '\n')


if __name__ == '__main__':
    main()
