"""Reference-checked common-kernel benchmark; run unchanged against old/new wheels."""
import argparse
import gc
import hashlib
import json
import platform
import statistics
import timeit
import tracemalloc
from pathlib import Path

import numpy as np
from tightarray import Array
from tightarray import array_api as xp


def measure(fn, expected):
    result = fn()
    np.testing.assert_array_equal(result, expected)
    timer = timeit.Timer(fn)
    loops = 1
    while loops < 65536 and timer.timeit(loops) < .003:
        loops *= 2
    samples = [timer.timeit(loops) * 1e9 / loops for _ in range(7)]
    gc.collect()
    tracemalloc.start()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(ns=statistics.median(samples), samples_ns=samples, loops=loops, traced_peak_bytes=peak)


def run(bits, n):
    values = (np.arange(n, dtype=np.uint64) * 13 % (1 << bits)).astype(np.uint8)
    middle = n // 2
    cases = {'python-list': values.tolist(), 'numpy-u8': values.copy(),
             'native-packed': Array(values, bits=bits),
             'native-aligned': Array(values, bits=bits, layout='word-aligned'),
             'array-api': xp.asarray(values)}
    rows = []
    for name, a in cases.items():
        def pair():
            old = int(a[middle])
            a[middle] = (old + 1) % (1 << bits)
            a[middle] = old
            return old
        if name.startswith('native'):
            summation = a.sum if hasattr(a, 'sum') else lambda: sum(a)
        elif name == 'array-api':
            summation = lambda: int(xp.sum(a))
        elif name == 'numpy-u8':
            summation = lambda: int(a.sum(dtype=np.uint64))
        else:
            summation = lambda: sum(a)
        operations = {'get-scalar': (lambda: int(a[middle]), int(values[middle])),
                      'set-restore': (pair, int(values[middle])),
                      'sum': (summation, int(values.sum(dtype=np.uint64)))}
        if name in ('array-api', 'numpy-u8'):
            view = a[17:81:2]
            operations['small-view-to-numpy'] = (lambda: np.array(view, copy=True), values[17:81:2])
            operations['strided-sum'] = ((lambda: int(xp.sum(a[::3]))) if name == 'array-api' else (lambda: int(a[::3].sum(dtype=np.uint64))), int(values[::3].sum(dtype=np.uint64)))
            def bulk():
                a[17:81:2] = values[17:81:2]
                return int(a[17])
            operations['assign-32'] = (bulk, int(values[17]))
        for method, (fn, expected) in operations.items():
            rows.append(dict(bits=bits, n=n, library=name, method=method,
                             input_sha256=hashlib.sha256(values.tobytes()).hexdigest(),
                             **measure(fn, expected)))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    rows = []
    for bits, n in [(b, 65536) for b in range(1, 9)] + [(5, 128), (5, 1048576)]:
        rows.extend(run(bits, n))
        print(f'{args.label}: bits={bits}, n={n}', flush=True)
    Path(args.output).write_text(json.dumps(dict(label=args.label, python=platform.python_version(),
        numpy=np.__version__, machine=platform.machine(), platform=platform.platform(), rows=rows), indent=2) + '\n')
