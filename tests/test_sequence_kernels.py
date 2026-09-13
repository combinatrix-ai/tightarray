import random
import numpy as np
import pytest
from tightarray import Array

@pytest.mark.parametrize('base',[2,4,20,21,32,256])
def test_rolling(base):
    rng=random.Random(base);bits=(base-1).bit_length()
    for n in [0,1,2,31,65,129]:
        values=[rng.randrange(base) for _ in range(n)]
        for layout in ['packed','word-aligned']:
            for k in [1,2,3,7]:
                a=Array(values,bits=bits,layout=layout)
                actual=np.frombuffer(a._rolling_codes(k,base),dtype='<u8').tolist()
                expected=[sum(v*base**j for j,v in enumerate(values[i:i+k])) for i in range(max(n-k+1,0))]
                assert actual==expected
                assert np.frombuffer(a[1:]._rolling_codes(k,base),dtype='<u8').tolist()==[sum(v*base**j for j,v in enumerate(values[i:i+k])) for i in range(1,max(n-k+1,1))]

@pytest.mark.parametrize('bits',range(1,9))
def test_hamming(bits):
    rng=np.random.default_rng(bits);width=(64//bits)*2
    x=rng.integers(0,1<<bits,(19,width),dtype=np.uint8)
    x[1]=x[0];x[2]=x[0];x[2,0]^=1
    a=Array(x.ravel(),bits=bits,layout='word-aligned')
    for cutoff in [0,2,254]:
        actual=np.frombuffer(a._hamming_rows(width,cutoff),dtype=np.uint8).reshape(19,19)
        expected=(x[:,None,:]!=x[None,:,:]).sum(axis=2);expected=np.where(expected<=cutoff,expected+1,0)
        np.testing.assert_array_equal(actual,expected)

def test_errors():
    a=Array([3],bits=2)
    for k,b in [(0,4),(1,1),(100,256),(1,2)]:
        with pytest.raises(ValueError):a._rolling_codes(k,b)
    for width,cutoff in [(0,1),(2,-1),(1,255),(1,1)]:
        with pytest.raises(ValueError):a._hamming_rows(width,cutoff)
