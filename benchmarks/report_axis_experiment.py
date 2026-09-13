"""Render reference-checked axis/stride measurements."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def read(name):
    rs=json.loads((root/'docs/results'/name).read_text())['rows']
    return {(r['bits'],r['layout'],r['case'],r['library']):r for r in rs}
b=read('m1-axis-before.json');a=read('m1-axis-after.json')
assert b.keys()==a.keys()
assert all(a[k]['input_sha256']==b[k]['input_sha256'] for k in a)
lines=['# Strided and axis reduction experiment','',
'Baseline: `bbd572d`. Apple M1 Pro, CPython 3.13.15, NumPy 2.5.3, one thread.',
'All inputs contain 65,536 random unsigned values. Views and input construction are',
'excluded from timing. Results are checked against NumPy before seven calibrated',
'samples. Array API timings include conversion of the result to a NumPy array.', '',
'## Five-bit results', '',
'| Operation | Previous packed µs | Packed µs | Aligned µs | NumPy µs |',
'| --- | ---: | ---: | ---: | ---: |']
for case in ['stride-2','stride-3','stride-4','stride-17','matrix-256x256-axis-0','matrix-256x256-axis-1','matrix-2048x32-axis-1','nd-axes-0-2']:
    old=b[(5,'packed',case,'array-api')]
    new=a[(5,'packed',case,'array-api')]
    aligned=a[(5,'word-aligned',case,'array-api')]
    control=a[(5,'packed',case,'numpy')]
    lines.append(f"| {case} | {old['ns']/1000:.2f} | {new['ns']/1000:.2f} | {aligned['ns']/1000:.2f} | {control['ns']/1000:.2f} |")
lines+=['','Axis 0 sums columns; axis 1 sums rows. The ND case has shape (16, 32, 128).', '',
'## Stride 3 across bit widths', '',
'| Bits | Packed µs | Aligned µs | NumPy µs |',
'| ---: | ---: | ---: | ---: |']
for bits in range(1,9):
    rs=[a[(bits,layout,'stride-3',lib)] for layout,lib in [('packed','array-api'),('word-aligned','array-api'),('packed','numpy')]]
    lines.append('| '+str(bits)+' | '+' | '.join(f"{r['ns']/1000:.2f}" for r in rs)+' |')
lines+=['','## Allocation during reduction', '',
'| Five-bit packed operation | Before traced peak B | After traced peak B |',
'| --- | ---: | ---: |']
for case in ['stride-3','matrix-256x256-axis-0','matrix-256x256-axis-1','matrix-2048x32-axis-1','nd-axes-0-2']:
    k=(5,'packed',case,'array-api')
    lines.append(f"| {case} | {b[k]['traced_peak_bytes']} | {a[k]['traced_peak_bytes']} |")
lines+=['','Tracemalloc is not RSS: C stack allocations are excluded. Axis kernels retain only',
'the required result plus rank-bounded descriptors and at most a 1 KiB decode buffer.',
'The input is never fully expanded on these native reduction paths.', '',
'## Native paths and limits', '',
'- Packed bool/uint8 sums support one axis, tuples of axes, negative axes, empty axes, empty input and keepdims. Default accumulation and explicit uint64 use C; other requested dtypes still use NumPy.',
'- Strides 2/3/4 use fixed masks over byte-aligned packed groups or physical aligned words when the starting offset permits. Other offsets use a generic masked or scalar reader.',
'- Negative strides are traversed in reverse order and zero strides use multiplication. Integer addition is exact within the uint64 accumulator, modulo overflow.',
'- Generic masked groups require at least four selected lanes; applying them to stride 17 on 2/3-bit values was slower and was rejected.',
'- Column reductions decode contiguous column tiles, then accumulate into uint64 outputs. Many short contiguous rows are decoded together. Other ND layouts traverse reduction runs.',
'- Large strides, arbitrary starting offsets, some row shapes, and general multi-axis layouts still have room for improvement. These results do not claim a win for every shape or dtype.', '',
'## Reproduce', '', '```sh',
'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python benchmarks/axis_experiment.py --label current --output axis.json',
'python benchmarks/report_axis_experiment.py', '```', '',
'Run the same harness against baseline and current wheels in the same environment.',
'Raw results: [before](results/m1-axis-before.json), [after](results/m1-axis-after.json).','']
(root/'docs/axis-performance.md').write_text('\n'.join(lines))
