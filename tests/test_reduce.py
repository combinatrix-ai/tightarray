import itertools
import numpy as np
import pytest
from tightarray import Array
from tightarray import array_api as xp


@pytest.mark.parametrize('bits,layout', list(itertools.product(range(1, 9), ['packed', 'word-aligned'])))
def test_strided_sum_all_widths(bits,layout):
    rng=np.random.default_rng(180)
    ref=rng.integers(0,1<<bits,10003,dtype=np.uint8)
    root=Array(ref,bits=bits,layout=layout)[7:]
    for step in [-257,-17,-7,-4,-3,-2,-1,0,1,2,3,4,7,17,257]:
        for n in [0,1,3,31,32,33]:
            start=9000 if step<0 else 1
            idx=start+np.arange(n)*step
            assert root._view_sum((n,),(step,),start)==int(ref[7:][idx].sum(dtype=np.uint64))
    for step in [2,3,4,7]:
        n=(len(root)-1)//step
        assert root._view_sum((n,),(step,),1)==int(ref[8:8+n*step:step].sum())


@pytest.mark.parametrize('bits,layout', list(itertools.product(range(1, 9), ['packed', 'word-aligned'])))
def test_axis_reductions(bits,layout):
    rng=np.random.default_rng(43)
    ref=rng.integers(0,1<<bits,(7,11,13),dtype=np.uint8)
    a=xp.reshape(xp.asarray(Array(ref.ravel(),bits=bits,layout=layout)),ref.shape)
    for axes in [None,(),0,1,2,-1,(0,2),(2,0),(0,1,2)]:
        for keep in [False,True]:
            for view,expected in [(a,ref),(a[::-1,::2,::-2],ref[::-1,::2,::-2]),(xp.permute_dims(a,(2,1,0)),ref.transpose(2,1,0))]:
                result=xp.sum(view,axis=axes,keepdims=keep)
                np.testing.assert_array_equal(np.asarray(result),expected.sum(axis=axes,keepdims=keep,dtype=np.uint64))
                result[...] = 0  # reduction outputs must remain writable
    matrix_ref=np.resize(ref,(41,1031))
    matrix=xp.reshape(xp.asarray(Array(matrix_ref.ravel(),bits=bits,layout=layout)),matrix_ref.shape)
    for v,r in [(matrix,matrix_ref),(matrix[::-2],matrix_ref[::-2])]:
        np.testing.assert_array_equal(np.asarray(xp.sum(v,axis=0)),r.sum(axis=0,dtype=np.uint64))


@pytest.mark.parametrize('dtype',[np.uint8,np.bool_])
def test_empty_scalar_axes_and_validation(dtype):
    for shape in [(),(0,),(1,0),(0,3),(2,0,3)]:
        r=np.zeros(shape,dtype=dtype); a=xp.asarray(r)
        for axes in [(),None]+list(range(len(shape))):
            np.testing.assert_array_equal(np.asarray(xp.sum(a,axis=axes)),r.sum(axis=axes))
    a=xp.asarray(np.ones((2,3),dtype=dtype))
    for axes in [(0,0),(0,-2),3,-3]:
        with pytest.raises(ValueError):xp.sum(a,axis=axes)
    for axes in [True,1.5]:
        with pytest.raises(TypeError):xp.sum(a,axis=axes)
    assert xp.sum(a,axis=0,dtype=xp.uint8).dtype==np.dtype('uint8')


def test_reduce_buffer_validation_and_unaligned_output():
    a=Array(range(8),bits=3)
    out=bytearray(17)
    a._view_reduce((2,4),(4,1),0,(1,),memoryview(out)[1:])
    assert np.frombuffer(out,dtype=np.uint64,offset=1).tolist()==[6,22]
    for axes,buffer in [((2,),bytearray(16)),((0,0),bytearray(16)),((1,),bytearray(8))]:
        before=bytes(buffer)
        with pytest.raises(ValueError):a._view_reduce((2,4),(4,1),0,axes,buffer)
        assert bytes(buffer)==before


@pytest.mark.parametrize('bits,layout', list(itertools.product(range(1,9),['packed','word-aligned'])))
def test_short_row_tiles(bits,layout):
    rng=np.random.default_rng(581)
    for shape in [(129,1),(2051,3),(129,17),(129,31),(128,32)]:
        ref=rng.integers(0,1<<bits,shape,dtype=np.uint8)
        a=xp.reshape(xp.asarray(Array(ref.ravel(),bits=bits,layout=layout)),shape)
        np.testing.assert_array_equal(np.asarray(xp.sum(a,axis=1)),ref.sum(axis=1,dtype=np.uint64))


@pytest.mark.parametrize('bits,layout', list(itertools.product(range(1,9),['packed','word-aligned'])))
def test_sparse_fast_paths_exact_allocation_tails(bits,layout):
    rng=np.random.default_rng(971)
    for step in [2,3,4]:
        for n in [127,128,129,130,257,1023]:
            for prefix in [0,64//bits if layout=='word-aligned' else 8]:
                ref=rng.integers(0,1<<bits,prefix+(n-1)*step+1,dtype=np.uint8)
                a=Array(ref,bits=bits,layout=layout)[prefix:]
                expected=int(ref[prefix::step].sum(dtype=np.uint64))
                assert a._view_sum((n,),(step,),0)==expected
                assert a._view_sum((n,),(-step,),(n-1)*step)==expected
