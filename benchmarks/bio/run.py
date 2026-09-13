import argparse, csv, gzip, hashlib, importlib.metadata, json, os, resource, statistics, subprocess, sys, time, tracemalloc
from pathlib import Path
import numpy as np
ROOT=Path(os.environ['BIO_PILOT_ROOT'])
for name in ['immuneML','DeepRC','MotifBoost']:
    sys.path.insert(0,str(ROOT/'repos'/name))
from adapters import get_kmers,hamming,MotifPacked,encode_continuous,NumpyCodes
from tightarray import Array
AA='ACDEFGHIKLMNPQRSTVWY'


def sequences():
    p=ROOT/'repos/scirpy/src/scirpy/tests/data/hamming_test_data/hamming_WU3k_seqs.npy'
    return np.load(p,allow_pickle=False).tolist(),p


def digest(result):
    h=hashlib.sha256()
    def add(x):
        if hasattr(x,'tocsr'):
            x=x.tocsr();x.sort_indices();add(np.array(x.shape));add(x.indptr.astype('<i8'));add(x.indices.astype('<i8'));add(x.data.astype('<f8'))
        elif isinstance(x,tuple):
            for y in x:add(y)
        else:
            a=np.asarray(x);h.update(str(a.shape).encode());h.update(a.tobytes())
    add(result);return h.hexdigest()


def job(project,backend):
    seqs,path=sequences();info={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'sequences':len(seqs)}
    if project=='bionumpy':
        import bionumpy as bnp
        path=ROOT/'repos/bionumpy/example_data/big.fq.gz'
        with gzip.open(path,'rt') as f:lines=f.read().splitlines()
        all_seqs=lines[1::4];seqs=[s for s in all_seqs if set(s)<=set('ACGT')]
        encoded=bnp.as_encoded_array(seqs,bnp.DNAEncoding)
        info.update(input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),sequences=len(seqs),excluded_reads=len(all_seqs)-len(seqs),bases=sum(map(len,seqs)),k=21)
        method=bnp.get_kmers if backend=='baseline' else get_kmers
        def fn():
            codes=method(encoded,21).ravel().raw();return np.unique(codes,return_counts=True)
        return fn,info
    if project=='immuneml':
        import bionumpy as bnp
        from immuneML.encodings.kmer_frequency import BNPSequenceEncodingStrategies as strategies
        from immuneML.encodings.kmer_frequency.KmerFrequencyEncoder import KmerFrequencyVectorizer
        encoded=bnp.as_encoded_array(seqs,bnp.AminoAcidEncoding)
        if backend!='baseline':strategies._extract_continuous=encode_continuous
        if backend=='numpy':
            import adapters
            adapters.get_kmers=bnp.get_kmers
        def fn():
            labels,rows=strategies.encode_continuous_kmer(encoded,3)
            # Eight deterministic repertoire partitions; preserve the real vectorizer and feature order.
            vectorizer=KmerFrequencyVectorizer();matrix=vectorizer.fit_transform(labels,rows%8,8)
            return np.asarray(vectorizer.feature_names_),matrix
        return fn,info
    if project=='scirpy':
        from scirpy.ir_dist.metrics import HammingDistanceCalculator
        calc=HammingDistanceCalculator(n_jobs=1,n_blocks=1,cutoff=2)
        return (lambda:calc.calc_dist_mat(seqs)) if backend=='baseline' else (lambda:hamming(seqs,2)),info
    if project in ('motifboost','motifboost_ingest'):
        from motifboost.methods.motif import ngram_features
        from motifboost.sequences import PackedStringArray
        weights=np.arange(len(seqs))%5+1
        if project=='motifboost_ingest':
            if backend=='baseline':return lambda:ngram_features(seqs,count_weights=weights),dict(info,scope='default string input -> weighted normalized trigrams')
            return lambda:MotifPacked(seqs,AA).features(weights),dict(info,scope='string input -> encode/pack -> weighted normalized trigrams')
        if backend=='baseline':
            packed=PackedStringArray(list(AA));packed.bulk_append(seqs)
            info['retained_payload_bytes']=len(packed.data.tobytes())+packed.indices.nbytes
            fn=lambda:ngram_features(packed.get_all_strs(),count_weights=weights)
        else:
            packed=MotifPacked(seqs,AA)
            if backend=='numpy':packed.data=NumpyCodes(np.frombuffer(packed.data.tobytes(),dtype=np.uint8).copy())
            info['retained_payload_bytes']=packed.data.nbytes+packed.lengths.nbytes+packed.starts.nbytes
            fn=lambda:packed.features(weights)
        info['scope']='packed resident repertoire -> weighted normalized trigrams; no classifier training'
        return fn,info
    if project=='deeprc':
        import h5py
        from deeprc.dataset_readers import RepertoireDataset,no_sequence_count_scaling
        directory=ROOT/'repos/DeepRC/deeprc/datasets/example_dataset/repertoires'
        records=[];bounds=[];input_hash=hashlib.sha256()
        for path in sorted(directory.glob('*.tsv')):
            input_hash.update(path.name.encode());input_hash.update(path.read_bytes())
            start=len(records)
            with path.open() as f:records.extend(csv.DictReader(f,delimiter='\t'))
            bounds.append((start,len(records)))
        seqs=[r['amino_acid'] for r in records];counts=np.array([int(r['templates']) for r in records])
        lengths=np.array(list(map(len,seqs)));width=int(lengths.max());arr=np.full((len(seqs),width),-1,dtype=np.int8)
        for i,s in enumerate(seqs):arr[i,:len(s)]=[AA.index(c) for c in s]
        file=ROOT/'deeprc-empty.h5'
        if not file.exists():
            with h5py.File(file,'w'):pass
        ds=RepertoireDataset.__new__(RepertoireDataset);ds.filepath=str(file);ds.sample_sequences_start_end=np.array(bounds);ds.sequences_hdf5_key='sequences';ds.sequence_counts_hdf5_key='sequence_counts';ds.sequence_counts_scaling_fn=no_sequence_count_scaling;ds.inputformat='NCL'
        if backend=='baseline':
            ds.sampledata={'seq_lens':lengths,'sequence_counts':counts,'sequences':arr}
            fn=lambda:tuple(ds.get_sample(i) for i in range(len(bounds)))
            info['retained_sequence_bytes']=arr.nbytes
        else:
            encoded=arr.astype(np.uint8);encoded[arr<0]=31;packed=Array(encoded.ravel(),bits=5)
            info['retained_sequence_bytes']=packed.nbytes
            def fn():
                # Preserve the original HDF5 open and sample return contract.
                batches=[]
                for start,end in bounds:
                    with h5py.File(file,'r'):
                        out=np.frombuffer(packed[start*width:end*width].tobytes(),dtype=np.int8).copy().reshape(end-start,width);out[out==31]=-1
                        batches.append((out[:,:int(lengths[start:end].max())],lengths[start:end],no_sequence_count_scaling(counts[start:end])))
                return tuple(batches)
            del encoded,arr
        info.update(input_sha256=input_hash.hexdigest(),sequences=len(seqs),repertoires=len(bounds),scope='all provided example repertoires, resident get_sample; no training or randomized sampling')
        return fn,info
    if project=='compairr':
        from collections import defaultdict
        input_path=ROOT/'compairr-input.tsv';output_path=ROOT/('compairr-'+backend+'.tsv')
        with input_path.open('w') as f:
            f.write('repertoire_id\tsequence_id\tjunction_aa\tduplicate_count\n')
            for i,s in enumerate(seqs):
                for r in [i%8,(i+1)%8]:f.write(f'r{r}\ts{i}\t{s}\t{i%5+1}\n')
        if backend=='baseline':
            def fn():
                subprocess.run([str(ROOT/'repos/compairr/src/compairr'),'-m','-g','-t','1','-o',str(output_path),str(input_path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
                lines=output_path.read_text().splitlines();cols=lines[0].split('\t')[1:];out=np.zeros((8,8),dtype=np.int64)
                for line in lines[1:]:
                    row,*values=line.split('\t')
                    for col,value in zip(cols,values):out[int(row[1:]),int(col[1:])]=int(value)
                return out
        else:
            table=bytes.maketrans(AA.encode(),bytes(range(20)))
            def fn():
                entries=defaultdict(lambda:np.zeros(8,dtype=np.int64))
                with input_path.open() as f:
                    for row in csv.DictReader(f,delimiter='\t'):
                        s=row['junction_aa'];packed=Array(s.encode().translate(table),bits=5,layout='word-aligned')
                        entries[(len(s),packed._to_word_bytes(None))][int(row['repertoire_id'][1:])]+=int(row['duplicate_count'])
                out=np.zeros((8,8),dtype=np.int64)
                for counts in entries.values():out+=np.outer(counts,counts)
                return out
        info['scope']='exact overlap, ignore genes, count products, eight derived repertoires; CLI launch included for CompAIRR'
        return fn,info
    raise ValueError(project)


def run(project,backend,out):
    fn,info=job(project,backend);warm_start=time.perf_counter();expected=digest(fn());warm_s=time.perf_counter()-warm_start
    samples=[]
    for _ in range(5):
        start=time.perf_counter();value=fn();samples.append(time.perf_counter()-start);assert digest(value)==expected
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    childrss=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    tracemalloc.start();value=fn();_,peak=tracemalloc.get_traced_memory();tracemalloc.stop();assert digest(value)==expected
    result=dict(project=project,backend=backend,median_s=statistics.median(samples),samples_s=samples,warm_call_s=warm_s,traced_peak_bytes=peak,worker_peak_rss_bytes=rss,child_peak_rss_bytes=childrss,digest=expected,info=info,
                versions={n:importlib.metadata.version(n) for n in ['numpy','numba','bionumpy','scirpy','torch','tightarray']})
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('project');p.add_argument('backend',choices=['baseline','candidate','numpy']);p.add_argument('output',type=Path);a=p.parse_args();run(a.project,a.backend,a.output)
