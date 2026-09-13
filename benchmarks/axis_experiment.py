"""Reference-checked strided and axis reductions; setup and views excluded."""
import argparse,json,platform,hashlib
from pathlib import Path
import numpy as np
from tightarray import Array
from tightarray import array_api as xp
from core_experiment import measure
p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--output',required=True);args=p.parse_args()
rows=[]
for bits in range(1,9):
    rng=np.random.default_rng(473+bits)
    raw=rng.integers(0,1<<bits,65536,dtype=np.uint8)
    digest=hashlib.sha256(raw.tobytes()).hexdigest()
    for layout in ['packed','word-aligned']:
        flat=xp.asarray(Array(raw,bits=bits,layout=layout))
        cases=[]
        for step in [-3,2,3,4,17]:cases.append((f'stride-{step}',flat[::step],raw[::step],None))
        for shape in [(256,256),(64,1024),(2048,32)]:
            a=xp.reshape(flat,shape);r=raw.reshape(shape)
            for axis in [0,1]:cases.append((f'matrix-{shape[0]}x{shape[1]}-axis-{axis}',a,r,axis))
        a=xp.reshape(flat,(16,32,128));r=raw.reshape(16,32,128)
        cases.append(('nd-axes-0-2',a,r,(0,2)))
        for name,a,r,axis in cases:
            expected=r.sum(axis=axis,dtype=np.uint64)
            for lib in ['array-api','numpy']:
                if lib=='numpy' and layout=='word-aligned':continue
                fn=(lambda:np.asarray(xp.sum(a,axis=axis))) if lib=='array-api' else (lambda:r.sum(axis=axis,dtype=np.uint64))
                rows.append(dict(bits=bits,layout=layout,case=name,library=lib,input_sha256=digest,**measure(fn,expected)))
    print('bits',bits,flush=True)
Path(args.output).write_text(json.dumps(dict(label=args.label,python=platform.python_version(),numpy=np.__version__,rows=rows),indent=2)+'\n')
