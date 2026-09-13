"""Render the competitor benchmark JSON without averaging unrelated workloads."""
import csv,json,sys
from pathlib import Path
source=Path(sys.argv[1]); out=Path(sys.argv[2]);r=json.loads(source.read_text()); rows=r['rows']
fields=['group','bits','n','distribution','library','method','ns','payload_bytes','shallow_object_bytes','traced_result_bytes','traced_peak_bytes','loops']
with out.with_suffix('.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
text=['# Competitor performance on Apple M1 Pro','',
'All reported results passed reference checks before timing. Five timing samples per operation; median shown. Separate operations are not combined into a headline speedup.','',
f'Python {r["python"]}; {r["platform"]} {r["machine"]}. Source versions: '+', '.join(f'{k} {v}' for k,v in r['versions'].items() if v)+'.','',
'## 65,536 elements, uniform 5-bit values','',
'Values are identical across libraries. Payload excludes object headers and allocator overhead. Python list payload is its pointer array, excluding shared integer objects. Rust/C allocations may not be visible to tracemalloc. Shallow object size is not total retained memory.','',
'| Library | Payload KiB | Construct ms | Get ns | Set/restore ns | Copy µs | Count µs | Gather 256 µs | Sum µs | Equals µs |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
selected=[x for x in rows if x['group']=='vector' and x['bits']==5 and x['n']==65536 and x['distribution']=='uniform']
libs=list(dict.fromkeys(x['library'] for x in selected))
for lib in libs:
 d={x['method']:x for x in selected if x['library']==lib}
 def val(m,div):return f'{d[m]["ns"]/div:.3f}' if m in d else '—'
 text.append('| '+lib+' | '+f'{next(iter(d.values()))["payload_bytes"]/1024:.2f}'+' | '+' | '.join(val(m,div) for m,div in [('construct-from-list',1e6),('get-scalar',1),('set-restore-pair',1),('copy',1000),('count',1000),('gather-256',1000),('sum',1000),('equals',1000)])+' |')
text+=['','## 1-bit comparison','', '| Library | Payload KiB | Get ns | Copy µs | Count µs | Gather 256 µs | Equals µs |','|---|---:|---:|---:|---:|---:|---:|']
selected=[x for x in rows if x['group']=='vector' and x['bits']==1 and x['n']==65536 and x['distribution']=='uniform']
for lib in list(dict.fromkeys(x['library'] for x in selected)):
 d={x['method']:x for x in selected if x['library']==lib}
 text.append('| '+lib+' | '+f'{next(iter(d.values()))["payload_bytes"]/1024:.2f}'+' | '+' | '.join(f'{d[m]["ns"]/div:.3f}' if m in d else '—' for m,div in [('get-scalar',1),('copy',1000),('count',1000),('gather-256',1000),('equals',1000)])+' |')
for group in ['codec','matrix','ragged','set']:
 text+=['',f'## {group.capitalize()}','', '| Bits | N | Library | Method | µs/op |','|---:|---:|---|---|---:|']
 for x in rows:
  if x['group']==group:text.append(f'| {x["bits"]} | {x["n"]} | {x["library"]} | {x["method"]} | {x["ns"]/1000:.3f} |')
text+=['','## Coverage','',
'Executed Python libraries: bitarray, bitstring, bitformat, ml_dtypes, Blosc2, bitstruct (Python/C), cbitstruct, bpack, npstructures, intbitset. Baselines: list, bytes, array.array, NumPy, and both native tightarray layouts plus the Array API adapter.',
'',
'The benchmark covers construction, scalar get/set, independent copy/slice, count, gather, sum, equality, and conversion. It does not measure every API method, mutation under concurrency, or out-of-core workloads. Unsupported operations are absent rather than assigned an infinite time. There is no comparison with a biosequence application layer.',
'', '## Interpretation and reproducibility','',
'- Inputs: seeded uniform small unsigned integers; additional 95%-zero cases for bits 1, 5, 8. Sizes 4,096 and 65,536. Full width/distribution results and timing samples are in the companion JSON/CSV.',
'- Construction starts from an already materialized Python list for every library; creation of that input is excluded. Blosc2 includes conversion to ndarray.',
'- Copy and slice-copy produce independent data; NumPy/native view creation is not compared against copying.',
'- Scalar get includes Python call/conversion overhead. Set/restore measures two assignments and a confirming read. Packed Array API assignment currently copies/scatters the array, so this path is expected to be costly.',
'- Gather returns 256 values. NumPy/native gather receives prebuilt intp indices; bitarray receives a prebuilt Python index list. Libraries without a gather primitive use Python scalar loops, identified by the adapter source.',
'- Native Array sum currently uses Python iteration; bitarray sum uses count(1), and its gather uses native list indexing. Array API operations may unpack/compute/repack. Whole equality returns one bool for every backend.',
'- Codec pack starts from a Python list; unpack-to-list and unpack-to-ndarray are separate. NumPy packbits includes converting integers into individual bits, since it is not an arbitrary-width integer pack API.',
'- Set operations intentionally have their own section: order and duplicates are discarded. They are not array substitutes.',
'- Thread environment: OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=VECLIB_MAXIMUM_THREADS=NUMEXPR_NUM_THREADS=1; Blosc2 compression/decompression nthreads=1.',
'- Payload is encoded data size or pointer storage, not total process RAM. traced_result_bytes and traced_peak_bytes cover only allocations visible to tracemalloc; C/Rust private allocators can be absent. Do not rank total memory by shallow_object_bytes.',
'- PyFastPFor 1.4.0 could not build on ARM64: its bundled x86 intrinsic headers reject this architecture. No timing is invented for it.',
'- Julia BitArray is measured separately in competitors-julia.csv after JIT warmup. Its native Julia call overhead is different, so it is excluded from Python rankings.',
'- pysdsl had no PyPI distribution. Building official source and submodules failed in SDSL louds_tree.hpp (nonexistent m_select1/m_select0 members); no performance conclusion is drawn.',
'', 'Reproduce with `python benchmarks/competitors.py --output competitors.json`, using `benchmarks/competitors-requirements.txt`. Render with `python benchmarks/report_competitors.py competitors.json docs/competitor-performance.md`.','',
'For Julia: `python benchmarks/prepare_julia.py /tmp/competitor-inputs`, then `JULIA_NUM_THREADS=1 julia --startup-file=no benchmarks/competitors_julia.jl /tmp/competitor-inputs/julia-input.bin /tmp/competitor-inputs/julia-indices.txt competitors-julia.csv`.','']
julia=source.parent/'competitors-julia.csv'
if julia.exists():
    text+=['## Julia reference (separate runtime)','',
           'Same 65,536 binary values and 256 gather indices. Julia 1.13.0, one thread, after JIT warmup. These timings exclude Python interoperability and are not part of the Python ranking. Retained bytes use Julia summarysize.', '',
           '| Library | Method | µs/op | Retained bytes |', '|---|---|---:|---:|']
    for x in csv.DictReader(julia.open()):
        text.append(f'| {x["library"]} | {x["method"]} | {float(x["ns"])/1000:.3f} | {x["retained_bytes"]} |')
    text+=['']
out.write_text('\n'.join(text))
