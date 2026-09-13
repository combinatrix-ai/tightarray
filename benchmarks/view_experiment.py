"""C-view scalar and width-growth measurements; setup excluded from width timing."""
import argparse
import gc
import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path
import numpy as np
from tightarray import Array
from tightarray import array_api as xp
from core_experiment import measure

p = argparse.ArgumentParser()
p.add_argument('--label', required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
rows = []
for layout in ('packed', 'word-aligned'):
    for n in (128, 65536, 1048576):
        for old, new in [(1, 2), (3, 5), (5, 8)]:
            values = (np.arange(n, dtype=np.uint64) % (1 << old)).astype(np.uint8)
            def fresh():
                return xp.asarray(Array(values, bits=old, layout=layout))
            samples = []
            for _ in range(9):
                x = fresh()
                start = time.perf_counter_ns()
                x[n//2] = (1 << new) - 1
                samples.append(time.perf_counter_ns() - start)
            expected = values.copy()
            expected[n//2] = (1 << new) - 1
            np.testing.assert_array_equal(np.asarray(x), expected)
            x = fresh()
            gc.collect()
            tracemalloc.start()
            x[n//2] = (1 << new) - 1
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            rows.append(dict(method='widen', layout=layout, n=n, old_bits=old, new_bits=new,
                ns=statistics.median(samples), samples_ns=samples, traced_peak_bytes=peak,
                output_payload_bytes=x.storage_nbytes))
for name in ('numpy-u8', 'array-api'):
    ref = np.arange(65536, dtype=np.uint8).reshape(256, 256) % 32
    x = ref.copy() if name == 'numpy-u8' else xp.asarray(ref)
    def pair():
        v = int(x[127, 131])
        x[127, 131] = 31
        x[127, 131] = v
        return v
    for method, fn in [('matrix-get', lambda: int(x[127,131])), ('matrix-set-restore', pair)]:
        rows.append(dict(method=method, library=name, **measure(fn, int(ref[127,131]))))
Path(a.output).write_text(json.dumps(dict(label=a.label, python=platform.python_version(), numpy=np.__version__, rows=rows), indent=2)+'\n')
