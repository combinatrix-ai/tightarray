import numpy as np
from tightarray import Array


def get_kmers(sequence,k):
    from bionumpy.encoded_array import EncodedArray,EncodedRaggedArray
    from bionumpy.encodings.kmer_encodings import KmerEncoding
    base=sequence.encoding.alphabet_size
    lengths=np.asarray(sequence.lengths)
    sizes=np.maximum(lengths-k+1,0)
    starts=np.r_[0,np.cumsum(lengths[:-1])]
    total=int(sizes.sum())
    flat=sequence.ravel().raw().astype(np.uint8,copy=False)
    packed=Array(flat,bits=(base-1).bit_length())
    codes=np.frombuffer(packed._rolling_codes(k,base),dtype='<u8').view(np.int64)
    positions=np.repeat(starts,sizes)+np.arange(total)-np.repeat(np.r_[0,np.cumsum(sizes[:-1])],sizes)
    return EncodedRaggedArray(EncodedArray(codes[positions],KmerEncoding(sequence.encoding,k)),sizes)


def hamming(seqs,cutoff=2):
    from scipy.sparse import coo_matrix
    lengths=np.array([len(s) for s in seqs]);alphabet=sorted(set(''.join(seqs)))
    lut=np.zeros(256,dtype=np.uint8)
    for i,s in enumerate(alphabet):lut[ord(s)]=i
    bits=max(1,(len(alphabet)-1).bit_length());lanes=64//bits
    rows=[];cols=[];vals=[]
    for length in np.unique(lengths):
        idx=np.flatnonzero(lengths==length);n=len(idx)
        width=max(lanes,((int(length)+lanes-1)//lanes)*lanes)
        data=np.zeros((n,width),dtype=np.uint8)
        if length:
            raw=np.frombuffer(''.join(seqs[i] for i in idx).encode('ascii'),dtype=np.uint8).reshape(n,int(length))
            data[:,:length]=lut[raw]
        packed=Array(data.ravel(),bits=bits,layout='word-aligned')
        distances=np.frombuffer(packed._hamming_rows(width,cutoff),dtype=np.uint8).reshape(n,n)
        r,c=np.nonzero(distances);rows.append(idx[r]);cols.append(idx[c]);vals.append(distances[r,c])
    return coo_matrix((np.concatenate(vals),(np.concatenate(rows),np.concatenate(cols))),shape=(len(seqs),len(seqs))).tocsr()


class MotifPacked:
    def __init__(self,seqs,alphabet):
        self.base=len(alphabet)+1
        lut=np.zeros(256,dtype=np.uint8)
        for i,s in enumerate(alphabet,1):lut[ord(s)]=i
        self.lengths=np.array([len(s)+2 for s in seqs],dtype=np.int64)
        self.starts=np.r_[0,np.cumsum(self.lengths[:-1])]
        # Reverse each bounded sequence to match MotifBoost's most-significant-first index convention.
        raw=''.join('@'+s[::-1]+'@' for s in seqs).encode('ascii')
        self.data=Array(lut[np.frombuffer(raw,dtype=np.uint8)],bits=(self.base-1).bit_length())
    def features(self,weights,k=3):
        sizes=np.maximum(self.lengths-k+1,0);n=int(sizes.sum())
        positions=np.repeat(self.starts,sizes)+np.arange(n)-np.repeat(np.r_[0,np.cumsum(sizes[:-1])],sizes)
        codes=np.frombuffer(self.data._rolling_codes(k,self.base),dtype='<u8')[positions]
        counts=np.bincount(codes.astype(np.int64),weights=np.repeat(weights,sizes),minlength=self.base**k)
        return counts/counts.sum()


def encode_continuous(seq_array,k):
    kmers=get_kmers(seq_array,k)
    codes=kmers.ravel().raw();base=seq_array.encoding.alphabet_size
    alphabet=np.array(list(bytes(seq_array.encoding._alphabet).decode('ascii')))
    # Materialize only observed labels, rather than the entire alphabet**k vocabulary.
    labels=alphabet[codes%base]
    for j in range(1,k):labels=np.char.add(labels,alphabet[(codes//(base**j))%base])
    return labels,np.repeat(np.arange(len(seq_array)),np.maximum(np.asarray(seq_array.lengths)-k+1,0))


class NumpyCodes:
    """Ablation: identical numeric pipeline with resident uint8 NumPy storage."""
    def __init__(self,values):
        self.values=values
        self.nbytes=values.nbytes
    def _rolling_codes(self,k,base):
        view=np.lib.stride_tricks.sliding_window_view(self.values,k)
        return (view @ (np.uint64(base)**np.arange(k,dtype=np.uint64))).astype('<u8').tobytes()
