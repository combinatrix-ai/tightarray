"""Separate Scirpy's compiled inner kernel from per-call JIT/setup overhead."""
import json,time,statistics
from pathlib import Path
from run import ROOT,sequences,digest
from scirpy.ir_dist import metrics
seqs,_=sequences();captured=[];original=metrics.nb.jit

def capturing(*args,**kwargs):
    decorator=original(*args,**kwargs)
    def wrap(fn):
        compiled=decorator(fn)
        if fn.__name__=='_nb_hamming_mat':captured.append(compiled)
        return compiled
    return wrap

metrics.nb.jit=capturing
try:reference=metrics.HammingDistanceCalculator(n_jobs=1,n_blocks=1,cutoff=2).calc_dist_mat(seqs)
finally:metrics.nb.jit=original
assert len(captured)==1
fn=captured[0];fn();samples=[]
for _ in range(7):
    start=time.perf_counter();result=fn();samples.append(time.perf_counter()-start)
out=dict(median_s=statistics.median(samples),samples_s=samples,scope='cached compiled inner kernel on captured fixed input; excludes encoding/JIT/CSR assembly',reference_digest=digest(reference))
(ROOT/'scirpy-compiled.json').write_text(json.dumps(out,indent=2)+'\n');print(out)
