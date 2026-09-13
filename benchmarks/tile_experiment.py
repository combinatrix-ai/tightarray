"""Sweep reduction boundaries and offsets; compare identical random inputs."""
import argparse,json,platform
from pathlib import Path
import numpy as np
from tightarray import Array
from tightarray import array_api as xp
from core_experiment import measure
p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--output',required=True);p.add_argument('--bits',default='1,2,3,4,5,6,7,8');args=p.parse_args()
rows=[]
for bits in map(int,args.bits.split(',')):
    rng=np.random.default_rng(348+bits)
    for width in [16,31,32,33,63,64,65,128,256,1024]:
        height=max(64,65536//width)
        for offset in [0,1,7]:
            values=rng.integers(0,1<<bits,height*width+offset,dtype=np.uint8)
            ref=values[offset:].reshape(height,width)
            for layout in ['packed','word-aligned']:
                root=xp.asarray(Array(values,bits=bits,layout=layout))
                a=xp.reshape(root[offset:],ref.shape)
                for axis in [0,1]:
                    for lib in ['array-api','numpy']:
                        if lib=='numpy' and layout=='word-aligned':continue
                        fn=(lambda:np.asarray(xp.sum(a,axis=axis))) if lib=='array-api' else (lambda:ref.sum(axis=axis,dtype=np.uint64))
                        rows.append(dict(bits=bits,width=width,height=height,offset=offset,layout=layout,axis=axis,library=lib,**measure(fn,ref.sum(axis=axis,dtype=np.uint64))))
    print(bits,flush=True)
Path(args.output).write_text(json.dumps(dict(label=args.label,python=platform.python_version(),numpy=np.__version__,rows=rows),indent=2)+'\n')
