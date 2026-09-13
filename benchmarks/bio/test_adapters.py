from collections import Counter
import numpy as np
import bionumpy as bnp
from adapters import get_kmers,encode_continuous,hamming,MotifPacked


def test_kmers_and_labels():
    for alphabet,encoding in [('ACGT',bnp.DNAEncoding),('ACDEFGHIKLMNPQRSTVWY',bnp.AminoAcidEncoding)]:
        seqs=[alphabet,alphabet[::-1],alphabet[:7]]
        encoded=bnp.as_encoded_array(seqs,encoding)
        for k in [1,2,3,5]:
            old=bnp.get_kmers(encoded,k);new=get_kmers(encoded,k)
            np.testing.assert_array_equal(old.ravel().raw(),new.ravel().raw())
            np.testing.assert_array_equal(old.lengths,new.lengths)
            labels,rows=encode_continuous(encoded,k)
            assert labels.tolist()==[s[i:i+k] for s in seqs for i in range(len(s)-k+1)]
            assert rows.tolist()==[r for r,s in enumerate(seqs) for _ in range(len(s)-k+1)]


def test_hamming_sparse_semantics():
    seqs=['AAA','ACA','CCC','AAA','AC','C','']
    for cutoff in [0,1,2]:
        actual=hamming(seqs,cutoff).toarray()
        expected=np.zeros(actual.shape,dtype=np.uint8)
        for i,a in enumerate(seqs):
            for j,b in enumerate(seqs):
                d=sum(x!=y for x,y in zip(a,b))
                if len(a)==len(b) and d<=cutoff:expected[i,j]=d+1
        np.testing.assert_array_equal(actual,expected)


def test_motif_boundaries_counts_and_orientation():
    alphabet='ACDEFGHIKLMNPQRSTVWY';seqs=['ACDE','WYAC','A','GGG'];weights=[1,5,2,3]
    p=MotifPacked(seqs,alphabet);lookup={c:i for i,c in enumerate('@'+alphabet)}
    for k in [2,3,4]:
        expected=np.zeros(21**k,dtype=np.float64)
        for s,w in zip(seqs,weights):
            s='@'+s+'@'
            for i in range(len(s)-k+1):
                code=sum(lookup[c]*21**(k-1-j) for j,c in enumerate(s[i:i+k]));expected[code]+=w
        expected/=expected.sum()
        np.testing.assert_array_equal(p.features(weights,k),expected)
