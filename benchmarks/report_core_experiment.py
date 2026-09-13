"""Render the recorded common-kernel experiment without rerunning timings."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def rows(name):
    data = json.loads((ROOT / 'docs/results' / name).read_text())
    return {(r['bits'], r['n'], r['library'], r['method']): r for r in data['rows']}

before = rows('m1-core-before.json')
after = rows('m1-core-after.json')
assert before.keys() == after.keys()
assert all(before[k]['input_sha256'] == after[k]['input_sha256'] for k in before)
lines = ['# Common-kernel performance experiment', '',
    'Apple M1 Pro, CPython 3.13.15, NumPy 2.5.3, one thread. Baseline: `b793d1f`.',
    'Times below are microseconds, medians of seven calibrated samples (at least 3 ms per sample, except the loop-count cap).',
    'Inputs and results are checked against NumPy before timing. Python and NumPy controls use the same harness in both runs.', '',
    '## Five-bit arrays, 65,536 values', '',
    '| API | Operation | Before µs | After µs | Speedup |',
    '| --- | --- | ---: | ---: | ---: |']
for lib, method in [('array-api', m) for m in ['get-scalar', 'set-restore', 'assign-32', 'small-view-to-numpy', 'sum', 'strided-sum']] + [('native-packed', 'sum'), ('native-aligned', 'sum')]:
    key = (5, 65536, lib, method)
    a, b = before[key], after[key]
    lines.append(f"| {lib} | {method} | {a['ns']/1000:.3f} | {b['ns']/1000:.3f} | {a['ns']/b['ns']:.1f}× |")
lines += ['', '`set-restore` includes an integer read and two assignments. `assign-32` writes 32 strided elements.',
    'No timed assignment increases storage width. The small conversion copies a preexisting 32-element view.',
    'Native sum changes from Python `sum(a)` to the new `a.sum()` kernel; Array API retains the same `xp.sum(a)` call.', '',
    '## Continuous sum across widths, 65,536 values', '',
    '| Bits | NumPy uint8 µs | Native packed µs | Native aligned µs | Array API µs |',
    '| ---: | ---: | ---: | ---: | ---: |']
for bits in range(1, 9):
    times = [after[(bits, 65536, lib, 'sum')]['ns']/1000 for lib in ['numpy-u8', 'native-packed', 'native-aligned', 'array-api']]
    lines.append('| '+str(bits)+' | '+' | '.join(f'{t:.3f}' for t in times)+' |')
lines += ['', '## Scalar complexity and traced allocation', '',
    '| Values | Read µs | Set/restore µs | Read peak B | Set peak B | Sum peak B |',
    '| ---: | ---: | ---: | ---: | ---: | ---: |']
for n in (128, 65536, 1048576):
    a,b,c = [after[(5,n,'array-api',m)] for m in ['get-scalar','set-restore','sum']]
    lines.append(f"| {n:,} | {a['ns']/1000:.3f} | {b['ns']/1000:.3f} | {a['traced_peak_bytes']} | {b['traced_peak_bytes']} | {c['traced_peak_bytes']} |")
lines += ['', 'These are `tracemalloc` peaks per operation, not process RSS or total native memory. C stack storage is excluded:',
    'the view descriptor uses approximately 1 KiB at its maximum supported rank. Reduction creates no decoded array.',
    'Retained payload layouts are unchanged (5-bit packed uses approximately 5/8 of uint8 payload).', '',
    '## Limits', '',
    '- Array API scalar operations still create Python view/dtype objects and remain slower than NumPy scalars.',
    '- The 6-bit Array API sum is approximately tied with NumPy in this run; small differences are not a robust win.',
    '- Strided sum remains slower than NumPy, although the first experimental regression was removed.',
    '- Widening storage is still O(n) and temporarily decodes the root; the constant-time mutation claim excludes widening.',
    '- Other axis/dtype reductions and advanced indexing still use NumPy fallbacks.',
    '- This warm-cache deterministic periodic workload is not a replacement for random/skewed competitor benchmarks.', '',
    '## Reproduction', '', '```sh',
    'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python benchmarks/core_experiment.py --label current --output current.json',
    'python benchmarks/report_core_experiment.py', '```', '',
    'Run the same benchmark script with baseline and current wheels in the same environment.',
    'Raw data: [before](results/m1-core-before.json), [after](results/m1-core-after.json).',
    'Architecture and rejected alternatives: [shared kernels](shared-kernels.md).', '']
(ROOT/'docs/core-performance.md').write_text('\n'.join(lines))
