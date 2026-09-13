"""Reference-checked method benchmarks; no timing ratios across unlike operations."""
import argparse, array, gc, hashlib, importlib.metadata, json, platform, random, statistics, sys, time, timeit, tracemalloc
from pathlib import Path
import numpy as np
from tightarray import Array, Matrix, RaggedArray
from tightarray import array_api as xp
import bitarray, bitstring, bitformat, blosc2, ml_dtypes, bitstruct, cbitstruct
from npstructures import RaggedArray as NPRagged


def plain(x):
    if isinstance(x, (list, tuple)): return [plain(v) for v in x]
    if isinstance(x, np.ndarray): return x.tolist()
    if hasattr(x, 'to_list'): return x.to_list()
    if hasattr(x, 'tolist'): return x.tolist()
    if isinstance(x, (np.generic,)): return x.item()
    return x


def timing(fn):
    fn()
    timer = timeit.Timer(fn)
    loops = 1
    while loops < 65536 and timer.timeit(loops) < .003: loops *= 2
    samples = [timer.timeit(loops) * 1e9 / loops for _ in range(5)]
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    result = fn()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(ns=statistics.median(samples), samples_ns=samples, loops=loops,
                traced_result_bytes=max(0,current-before), traced_peak_bytes=max(0,peak-before))


ROWS=[]
ONLY=set()
def record(group,bits,n,distribution,name,method,fn,expected,**metadata):
    got=plain(fn())
    if got != expected:
        raise AssertionError((group,bits,n,name,method,str(got)[:100],str(expected)[:100]))
    row=dict(group=group,bits=bits,n=n,distribution=distribution,library=name,method=method,**metadata)
    row.update(timing(fn)); ROWS.append(row)


def run_vector(bits,n,distribution):
    rng=random.Random(982+bits+n)
    values=[rng.randrange(1<<bits) if distribution=='uniform' or rng.random()<.05 else 0 for _ in range(n)]
    raw=bytes(values); a_np=np.array(values,dtype=np.uint8)
    value=(1<<bits)-1; middle=n//2; lo=n//4; hi=3*n//4
    indexes=[rng.randrange(n) for _ in range(256)]; npidx=np.array(indexes,dtype=np.intp)
    cases={
        'python-list':(lambda:list(values),lambda a:len(a)*8),
        'python-bytes':(lambda:bytes(values),lambda a:len(a)),
        'array-B':(lambda:array.array('B',values),lambda a:a.buffer_info()[1]*a.itemsize),
        'numpy-u8':(lambda:np.array(values,dtype=np.uint8),lambda a:a.nbytes),
        'tightarray-packed':(lambda:Array(values,bits=bits,layout='packed'),lambda a:a.nbytes),
        'tightarray-aligned':(lambda:Array(values,bits=bits,layout='word-aligned'),lambda a:a.nbytes),
        'tightarray-api':(lambda:xp.asarray(values,dtype=xp.uint8),lambda a:a.storage_nbytes),
        'bitstring':(lambda:bitstring.Array(f'uint{bits}',values),lambda a:(len(a.data)+7)//8),
        'bitformat':(lambda:bitformat.Array(f'u{bits}',values),lambda a:(n*bits+7)//8),
        'blosc2-1thread':(lambda:blosc2.asarray(np.array(values,dtype=np.uint8),cparams={'nthreads':1},dparams={'nthreads':1}),lambda a:a.cbytes),
    }
    if bits==1: cases['bitarray']=(lambda:bitarray.bitarray(values),lambda a:a.buffer_info().nbytes)
    if bits in (1,2,4):
        dt=getattr(ml_dtypes,f'uint{bits}')
        cases[f'ml_dtypes-u{bits}']=(lambda:np.array(values,dtype=dt),lambda a:a.nbytes)
    for name,(factory,payload) in cases.items():
        if ONLY and name not in ONLY: continue
        obj=factory()
        if name.startswith('blosc'): unpack=lambda:obj[:].tolist()
        elif name in ('python-bytes','python-list'): unpack=lambda:list(obj)
        elif name=='tightarray-api': unpack=lambda:np.asarray(obj).tolist()
        else: unpack=lambda:plain(obj)
        assert unpack()==values,(name,'initial')
        mem={'payload_bytes':int(payload(obj)),'shallow_object_bytes':sys.getsizeof(obj),
             'input_sha256':hashlib.sha256(raw).hexdigest()}
        # Construction is always from a preexisting Python list, conversions included.
        def construct():
            a=factory()
            if name.startswith('blosc'): return a[:].tolist()
            if name in ('python-bytes','array-B','pysdsl'): return list(a)
            if name=='tightarray-api': return np.asarray(a).tolist()
            return plain(a)
        assert construct()==values
        row=dict(group='vector',bits=bits,n=n,distribution=distribution,library=name,method='construct-from-list',**mem)
        row.update(timing(factory)); ROWS.append(row)
        scalar=lambda:int(obj[middle])
        record('vector',bits,n,distribution,name,'get-scalar',scalar,values[middle],**mem)
        record('vector',bits,n,distribution,name,'to-list',unpack,values,**mem)
        # All copy rows produce independent storage; views are separate.
        if name=='python-bytes': copy=lambda:bytes(bytearray(obj)); tocopy=lambda a:list(a)
        elif name=='bitstring': copy=lambda:obj[:]; tocopy=plain
        elif name=='bitformat': copy=lambda:obj[:]; tocopy=plain
        elif name=='tightarray-api': copy=lambda:xp.asarray(obj,copy=True); tocopy=lambda a:np.asarray(a).tolist()
        elif name.startswith('blosc'): copy=lambda:obj.copy(); tocopy=lambda a:a[:].tolist()
        elif name=='array-B': copy=lambda:obj[:]; tocopy=lambda a:list(a)
        else: copy=lambda:obj.copy(); tocopy=plain
        assert tocopy(copy())==values
        row=dict(group='vector',bits=bits,n=n,distribution=distribution,library=name,method='copy',**mem);row.update(timing(copy));ROWS.append(row)
        if name.startswith('tightarray-') and name!='tightarray-api':
            count=lambda:obj.count(value); gather=lambda:obj.gather(npidx); summ=lambda:obj.sum()
        elif name=='bitarray':
            count=lambda:obj.count(value); gather=lambda:obj[indexes]; summ=lambda:obj.count(1)
        elif name in ('python-list','python-bytes','array-B','bitstring'):
            count=lambda:obj.count(value); gather=lambda:[int(obj[i]) for i in indexes]; summ=lambda:sum(obj)
        elif name=='bitformat':
            count=(lambda:obj.count(value)) if hasattr(obj,'count') else None
            gather=lambda:[int(obj[i]) for i in indexes]; summ=lambda:sum(obj)
        elif name=='tightarray-api':
            count=lambda:int(xp.sum(obj==value)); gather=lambda:np.asarray(xp.take(obj,npidx)).tolist(); summ=lambda:int(xp.sum(obj))
        elif name.startswith('blosc'):
            count=lambda:int((obj==value).sum());gather=lambda:obj[npidx];summ=lambda:int(obj.sum())
        else:
            count=lambda:int(np.count_nonzero(obj==value));gather=lambda:obj[npidx];summ=lambda:int(np.sum(obj,dtype=np.uint64))
        if count: record('vector',bits,n,distribution,name,'count',count,values.count(value),**mem)
        record('vector',bits,n,distribution,name,'gather-256',gather,[values[i] for i in indexes],**mem)
        if summ: record('vector',bits,n,distribution,name,'sum',summ,sum(values),**mem)
        if name!='python-bytes':
            old=values[middle]
            def mutate():
                obj[middle]=value
                obj[middle]=old
                return int(obj[middle])
            record('vector',bits,n,distribution,name,'set-restore-pair',mutate,old,**mem)
        # Whole-container equality has the same scalar Boolean result.
        if hasattr(obj,'equals'): eq=lambda:bool(obj.equals(copy()))
        elif isinstance(obj,np.ndarray): eq=lambda:bool(np.array_equal(obj,copy()))
        elif name=='tightarray-api': eq=lambda:bool(xp.all(obj==xp.asarray(obj,copy=True)))
        elif name.startswith('blosc'): eq=lambda:bool((obj==obj.copy()).all())
        else: eq=lambda:obj==copy()
        # Exclude copy cost: create an independent equal peer before timing.
        peer=copy()
        if hasattr(obj,'equals'): eq=lambda:bool(obj.equals(peer))
        elif isinstance(obj,np.ndarray): eq=lambda:bool(np.array_equal(obj,peer))
        elif name=='tightarray-api': eq=lambda:bool(xp.all(obj==peer))
        elif name.startswith('blosc'): eq=lambda:bool((obj==peer).all())
        else: eq=lambda:obj==peer
        record('vector',bits,n,distribution,name,'equals',eq,True,**mem)
        # slice-copy includes materialization on NumPy/native shared-view containers.
        if name.startswith('tightarray-') and name!='tightarray-api': slicer=lambda:obj[lo:hi].copy()
        elif name=='tightarray-api': slicer=lambda:xp.asarray(obj[lo:hi],copy=True)
        elif name.startswith('numpy') or name.startswith('ml_dtypes'): slicer=lambda:obj[lo:hi].copy()
        else: slicer=lambda:obj[lo:hi]
        a=slicer()
        normal=lambda a:np.asarray(a).tolist() if name=='tightarray-api' else list(a) if name in ('python-bytes','array-B') else plain(a)
        assert normal(a)==values[lo:hi],name
        row=dict(group='vector',bits=bits,n=n,distribution=distribution,library=name,method='slice-copy',**mem);row.update(timing(slicer));ROWS.append(row)
        print('done',bits,n,distribution,name,flush=True)


def run_codecs(bits,n):
    rng=random.Random(19+bits+n); values=[rng.randrange(1<<bits) for _ in range(n)]
    fmt=f'u{bits}'*n
    bs=bitstruct.compile(fmt)
    cases={'bitstruct-python':(lambda:bs.pack(*values),lambda data:list(bs.unpack(data))),
           'cbitstruct':(lambda:cbitstruct.pack(fmt,*values),lambda data:list(cbitstruct.unpack(fmt,data))),
           'tightarray-packed':(lambda:Array(values,bits=bits),lambda data:data.tolist()),
           'numpy-packbits':(lambda:np.packbits(np.array(values,dtype=np.uint8)[:,None] >> np.arange(bits-1,-1,-1,dtype=np.uint8)&1),
              lambda data:(np.unpackbits(data)[:n*bits].reshape(n,bits).astype(np.uint16) @ (1<<np.arange(bits-1,-1,-1))).tolist())}
    import bitstruct.c as bc
    cases['bitstruct-c']=(lambda:bc.pack(fmt,*values),lambda data:list(bc.unpack(fmt,data)))
    for name,(pack,unpack) in cases.items():
        encoded=pack(); assert unpack(encoded)==values
        for method,fn in [('pack-from-list',pack),('unpack-to-list',lambda:unpack(encoded))]:
            row=dict(group='codec',bits=bits,n=n,distribution='uniform',library=name,method=method,
                     payload_bytes=encoded.nbytes if isinstance(encoded,(Array,np.ndarray)) else len(encoded))
            row.update(timing(fn));ROWS.append(row)
    # bpack's sample codec has no matching pack API; compare ndarray decode separately.
    import bpack.np as bnp
    encoded=bs.pack(*values)
    expected=np.array(values).tolist()
    record('codec',bits,n,'uniform','bpack-numpy','unpack-to-ndarray',lambda:bnp.unpackbits(encoded,bits_per_sample=bits)[:n],expected)
    native=cases['tightarray-packed'][0]()
    record('codec',bits,n,'uniform','tightarray-packed','unpack-to-ndarray',lambda:np.asarray(native),expected)


def run_ragged(n):
    rng=random.Random(64+n); lengths=[rng.randrange(1,64) for _ in range(n//32)]
    rows=[[rng.randrange(32) for _ in range(k)] for k in lengths]
    flat=[v for row in rows for v in row]; k=len(rows)//2
    cases={'python-list':lambda:[list(row) for row in rows],
           'tightarray-packed':lambda:RaggedArray(rows,bits=5),
           'npstructures':lambda:NPRagged(rows,dtype=np.uint8)}
    for name,factory in cases.items():
        a=factory(); assert plain(a)==rows
        rowcopy=(lambda:list(a[k])) if name=='python-list' else (lambda:a[k].tolist())
        scalar=(lambda:int(a[k][0])) if name=='python-list' else (lambda:int(a[k,0]))
        unpack=(lambda:[list(row) for row in a]) if name=='python-list' else (lambda:a.tolist())
        operations={'get-row-to-list':rowcopy,'get-scalar':scalar,'to-list':unpack}
        expect={'get-row-to-list':rows[k],'get-scalar':rows[k][0],'to-list':rows}
        for method,fn in operations.items():record('ragged',5,len(flat),'uniform',name,method,fn,expect[method])
        row=dict(group='ragged',bits=5,n=len(flat),distribution='uniform',library=name,method='construct-from-rows');row.update(timing(factory));ROWS.append(row)


def run_sets(n):
    from intbitset import intbitset
    left=list(range(0,n,2));right=list(range(0,n,3))
    factories={'python-set':set,'intbitset':intbitset}
    for name,factory in factories.items():
        a=factory(left);b=factory(right)
        for method,fn,expected in [
            ('membership',lambda:(n//2 in a),n//2 in set(left)),
            ('intersection',lambda:sorted(a&b),sorted(set(left)&set(right))),
            ('union',lambda:sorted(a|b),sorted(set(left)|set(right)))]:
            assert fn()==expected
        # Sorted conversion is validation only, not part of timed set operations.
        for method,fn in [('membership',lambda:n//2 in a),('intersection',lambda:a&b),('union',lambda:a|b),('construct',lambda:factory(left))]:
            row=dict(group='set',bits=None,n=n,distribution='dense',library=name,method=method,
                     shallow_object_bytes=sys.getsizeof(a))
            row.update(timing(fn));ROWS.append(row)


def run_matrix(n):
    values=np.arange(n,dtype=np.uint8)%32
    rows=values.reshape(-1,64).tolist(); mid=len(rows)//2
    cases={'python-list':lambda:[list(r) for r in rows],
           'numpy-u8':lambda:np.array(rows,dtype=np.uint8),
           'tightarray-packed':lambda:Matrix(rows,bits=5),
           'tightarray-api':lambda:xp.asarray(rows,dtype=xp.uint8),
           'blosc2-1thread':lambda:blosc2.asarray(np.array(rows,dtype=np.uint8),cparams={'nthreads':1},dparams={'nthreads':1})}
    for name,factory in cases.items():
        a=factory()
        if name=='tightarray-api': unpack=lambda:np.asarray(a).tolist()
        elif name.startswith('blosc'): unpack=lambda:a[:].tolist()
        elif name=='python-list':unpack=lambda:[list(row) for row in a]
        else:unpack=lambda:a.tolist()
        assert unpack()==rows
        scalar=(lambda:int(a[mid][32])) if name=='python-list' else (lambda:int(a[mid,32]))
        record('matrix',5,n,'uniform',name,'get-scalar',scalar,rows[mid][32])
        record('matrix',5,n,'uniform',name,'to-list',unpack,rows)
        row=dict(group='matrix',bits=5,n=n,distribution='uniform',library=name,method='construct-from-rows');row.update(timing(factory));ROWS.append(row)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--only');p.add_argument('--sections',default='vector,codec,ragged,set,matrix');args=p.parse_args()
    sections=set(args.sections.split(','))
    global ONLY
    ONLY=set(args.only.split(',')) if args.only else set()
    packages=['numpy','bitarray','bitstring','bitformat','ml_dtypes','blosc2','bitstruct','cbitstruct','bpack','npstructures','intbitset','pyfastpfor','pysdsl','tightarray']
    versions={}
    for name in packages:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    output=dict(python=platform.python_version(),platform=platform.system(),machine=platform.machine(),versions=versions,
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),rows=ROWS)
    try:
        for n in (([128] if args.smoke else [4096,65536]) if 'vector' in sections else []):
            for bits in ([1,3,4,8] if args.smoke else range(1,9)):run_vector(bits,n,'uniform')
        if not args.smoke and 'vector' in sections:
            for bits in [1,5,8]:run_vector(bits,65536,'skewed')
        if not ONLY:
            if 'codec' in sections:
                for bits in [1,3,5,8]:run_codecs(bits,128 if args.smoke else 4096)
            if 'ragged' in sections: run_ragged(256 if args.smoke else 65536)
            if 'set' in sections: run_sets(256 if args.smoke else 65536)
            if 'matrix' in sections: run_matrix(256 if args.smoke else 65536)
    finally:Path(args.output).write_text(json.dumps(output,indent=2)+'\n')

if __name__=='__main__':main()
