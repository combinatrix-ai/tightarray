"""Render the recorded C-view experiment."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
def read(name):
    return json.loads((root/'docs/results'/name).read_text())['rows']
before=read('m1-cview-before.json'); after=read('m1-cview-after.json')
extra_before=read('m1-cview-width-before.json'); extra_after=read('m1-cview-width-after.json')
def key(r): return (r['bits'],r['n'],r['library'],r['method'])
b={key(r):r for r in before}; a={key(r):r for r in after}
assert a.keys()==b.keys()
assert all(a[k]['input_sha256']==b[k]['input_sha256'] for k in a)
lines=['# C Array API views and bounded-memory widening', '',
'Baseline: `758f6bf`. Apple M1 Pro, CPython 3.13.15, NumPy 2.5.3.',
'Control implementations and benchmark inputs are unchanged. Times are microseconds.', '',
'## Five-bit arrays, 65,536 elements', '',
'| Operation | Previous Array API µs | C view µs | NumPy µs |',
'| --- | ---: | ---: | ---: |']
for m in ['get-scalar','set-restore','assign-32','sum','strided-sum']:
    old,new,control=b[(5,65536,'array-api',m)],a[(5,65536,'array-api',m)],a[(5,65536,'numpy-u8',m)]
    lines.append(f"| {m} | {old['ns']/1000:.3f} | {new['ns']/1000:.3f} | {control['ns']/1000:.3f} |")
lines+=['','The scalar fast path accepts Python integer indices (including full ND index tuples)',
'and Python integer assignment values. NumPy scalar indices/values, slices, masks, and',
'other casts still use the Python/NumPy fallback. Set/restore includes one read and two writes.', '',
'## Matrix scalar operations, 256 × 256', '',
'| Operation | Previous Array API µs | C view µs | NumPy µs |',
'| --- | ---: | ---: | ---: |']
for m in ['matrix-get','matrix-set-restore']:
    old=next(r for r in extra_before if r['method']==m and r['library']=='array-api')
    new=next(r for r in extra_after if r['method']==m and r['library']=='array-api')
    control=next(r for r in extra_after if r['method']==m and r['library']=='numpy-u8')
    lines.append(f"| {m} | {old['ns']/1000:.3f} | {new['ns']/1000:.3f} | {control['ns']/1000:.3f} |")
lines+=['','## Width growth, 1,048,576 elements', '',
'| Layout | Width | Before µs | After µs | Before traced peak KiB | After traced peak KiB |',
'| --- | --- | ---: | ---: | ---: | ---: |']
for old,new in zip(extra_before,extra_after):
    if new.get('n')!=1048576: continue
    assert (old['layout'],old['old_bits'],old['new_bits'])==(new['layout'],new['old_bits'],new['new_bits'])
    lines.append(f"| {new['layout']} | {new['old_bits']} → {new['new_bits']} | {old['ns']/1000:.2f} | {new['ns']/1000:.2f} | {old['traced_peak_bytes']/1024:.1f} | {new['traced_peak_bytes']/1024:.1f} |")
lines+=['', 'Width timing excludes input construction and reports nine independent samples, each starting',
'with a fresh array. The entire result is checked against NumPy. These single-operation',
'measurements have more timer/cache noise than the calibrated scalar measurements.',
'Traced peak includes the required new packed allocation but excludes preexisting storage and C stack memory.',
'Repacking uses at most a 1 KiB stack buffer; expansion to 8 bits writes directly to the new allocation.',
'Growth remains O(n), and individual layout/width combinations may trade some speed for bounded temporary memory.', '',
'## Implementation boundary', '',
'- A GC-aware C base type owns Array API metadata and supplies indexing, assignment, integer/float conversion slots.',
'- Scalar views share a C storage cell. Its replacement allocation is published only after repacking completes.',
'- Shape and stride tuples remain Python objects. ND descriptors are still parsed for bulk kernels; this is not a complete native ND executor.',
'- NumPy-backed dtypes and general operations preserve their fallback behavior.',
'- Strided/axis kernels remain the next performance target. The benchmark does not establish wins for all indexing/casting forms.', '',
'## Reproduce', '', '```sh',
'python benchmarks/core_experiment.py --label current --output scalar.json',
'python benchmarks/view_experiment.py --label current --output width-and-matrix.json',
'python benchmarks/report_view_experiment.py', '```', '',
'Use the same script with baseline/current wheels, set OMP_NUM_THREADS, OPENBLAS_NUM_THREADS',
'and VECLIB_MAXIMUM_THREADS to 1, and run timings without concurrent jobs.',
'Raw measurements are in `docs/results/m1-cview-*.json`.', '']
(root/'docs/cview-performance.md').write_text('\n'.join(lines))
