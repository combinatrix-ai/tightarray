"""Render NumPy-front-door timing and memory measurements."""
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
run = json.loads((root / 'docs/results/m1-pro-numpy-api.json').read_text())
lines = ['# NumPy API measurements', '',
         'Apple M1 Pro; ' + run['metadata']['note'], '',
         'These timings include NumPy dispatch and unpacking, separately from direct native methods.', '',
         '`count_nonzero(ndarray)` needs no equality-mask allocation, unlike the value-count baseline in the native benchmark.', '',
         'Median microseconds per public NumPy call; lower is better.', '']
for n in (65536, 1048576):
    for bits in (2, 5, 7):
        lines += [f'## {n:,} elements, {bits} bits', '',
                  '| NumPy call | ndarray | Packed | Word-aligned |', '| --- | ---: | ---: | ---: |']
        for method in ('asarray', 'array_equal', 'count_nonzero', 'take', 'add'):
            rows = {r['implementation']: r for r in run['results']
                    if (r['elements'], r['bits'], r['method']) == (n, bits, method)}
            lines += [f'| {method} | ' + ' | '.join(f"{rows[name]['ns_op']/1000:.3f}" for name in ('numpy', 'packed', 'word-aligned')) + ' |']
        lines += ['']
lines += ['## Interpretation', '',
          '- Whole-array equality retains a packed-kernel advantage at these sizes.',
          '- NumPy take dispatch costs more than direct `.gather()` and is slower than take on an existing ndarray here.',
          '- Ufunc arithmetic unpacks first; it is interoperability, not an accelerated arithmetic kernel.',
          '- `np.asarray(ndarray)` can share storage; tightarray always creates an independent writable array.',
          '- Result retention and traced peak memory are recorded per method. Conversion peaks include intermediate bytes and a writable bytearray.', '',
          '[Raw samples and source hashes](results/m1-pro-numpy-api.json) · [Timing and memory CSV](results/numpy-api.csv)', '']
(root / 'docs/numpy-performance.md').write_text('\n'.join(lines))
columns = ['elements', 'bits', 'implementation', 'method', 'dataset_retained_bytes',
           'result_retained_bytes', 'additional_peak_bytes', 'ns_op', 'min_ns_op', 'max_ns_op', 'loops']
with (root / 'docs/results/numpy-api.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, columns, extrasaction='ignore', lineterminator='\n')
    writer.writeheader()
    writer.writerows(run['results'])
