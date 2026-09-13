import itertools
import numpy as np
import pytest
from tightarray import Array
from tightarray import array_api as xp


@pytest.mark.parametrize('bits,layout',list(itertools.product(range(1,9),['packed','word-aligned'])))
def test_accumulator_width_boundary(bits,layout):
    top=(1<<bits)-1
    boundary=65535//top
    for height in [boundary-1,boundary,boundary+1]:
        ref=np.full((height,9),top,dtype=np.uint8)
        root=xp.asarray(Array(np.concatenate((np.zeros(7,dtype=np.uint8),ref.ravel())),bits=bits,layout=layout))
        a=xp.reshape(root[7:],ref.shape)
        for v,r in [(a,ref),(a[::-1],ref[::-1]),(a[::2],ref[::2])]:
            np.testing.assert_array_equal(np.asarray(xp.sum(v,axis=0)),r.sum(axis=0,dtype=np.uint64))


@pytest.mark.parametrize('layout',['packed','word-aligned'])
def test_column_tile_tails(layout):
    rng=np.random.default_rng(141)
    for width in [1023,1024,1025,2049]:
        ref=rng.integers(0,32,(67,width),dtype=np.uint8)
        a=xp.reshape(xp.asarray(Array(ref.ravel(),bits=5,layout=layout)),ref.shape)
        np.testing.assert_array_equal(np.asarray(xp.sum(a,axis=0)),ref.sum(axis=0,dtype=np.uint64))


@pytest.mark.parametrize('bits,layout',list(itertools.product(range(1,9),['packed','word-aligned'])))
def test_row_dispatch_boundaries(bits,layout):
    rng=np.random.default_rng(45)
    for width in [31,32,33,63,64,65,127,128,129,255,256,257]:
        ref=rng.integers(0,1<<bits,(129,width),dtype=np.uint8)
        root=xp.asarray(Array(np.concatenate((np.zeros(7,dtype=np.uint8),ref.ravel())),bits=bits,layout=layout))
        a=xp.reshape(root[7:],ref.shape)
        np.testing.assert_array_equal(np.asarray(xp.sum(a,axis=1)),ref.sum(axis=1,dtype=np.uint64))


def test_uint32_batch_flush_without_large_input_allocation():
    height=(2**32-1)//255+1
    a=xp.asarray(np.full(8,255,dtype=np.uint8))
    # A repeated-row view exercises a sum above uint32 without a giant allocation.
    repeated=a._view((height,8),(0,1),0)
    np.testing.assert_array_equal(np.asarray(xp.sum(repeated,axis=0)),np.full(8,height*255,dtype=np.uint64))
