/* Axis reduction into a caller-owned uint64 buffer; input never fully expands. */
static PyObject *array_view_reduce(Array *a,PyObject *args) {
    PyObject *shape,*strides,*axes; Py_ssize_t offset; Py_buffer buffer; ArrayView v;
    if(!PyArg_ParseTuple(args,"OOnO!w*",&shape,&strides,&offset,&PyTuple_Type,&axes,&buffer)) return NULL;
    if(parse_view(a,shape,strides,offset,&v)<0) goto bad;
    unsigned char selected[VIEW_MAX_NDIM]={0};
    for(Py_ssize_t i=0;i<PyTuple_GET_SIZE(axes);i++) {
        Py_ssize_t axis=PyLong_AsSsize_t(PyTuple_GET_ITEM(axes,i)); if(PyErr_Occurred()) goto bad;
        if(axis<0 || axis>=v.ndim || selected[axis]) { PyErr_SetString(PyExc_ValueError,"invalid reduction axes"); goto bad; }
        selected[axis]=1;
    }
    ArrayView outer={0},inner={0}; outer.size=inner.size=1;
    for(Py_ssize_t d=0;d<v.ndim;d++) {
        ArrayView *part=selected[d]?&inner:&outer;
        if(v.shape[d] && part->size>PY_SSIZE_T_MAX/v.shape[d]) { PyErr_SetString(PyExc_OverflowError,"reduction shape overflow"); goto bad; }
        part->size*=v.shape[d]; part->shape[part->ndim]=v.shape[d]; part->stride[part->ndim++]=v.stride[d];
    }
    if(outer.size>PY_SSIZE_T_MAX/8 || buffer.len!=outer.size*8) { PyErr_SetString(PyExc_ValueError,"output buffer size mismatch"); goto bad; }
    if(outer.ndim==1 && inner.ndim==1 && inner.stride[0]==1 && inner.size>0 && inner.size<=32 && outer.stride[0]==inner.size && outer.size>=128) {
        uint8_t block[1024]; Py_ssize_t width=inner.size,rows=1024/width;
        for(Py_ssize_t base=0;base<outer.size;base+=rows) {
            Py_ssize_t count=outer.size-base<rows?outer.size-base:rows;
            unpack_range(a,v.offset+base*width,count*width,block);
            for(Py_ssize_t r=0;r<count;r++) {
                uint64_t total=0; Py_ssize_t j=0; const uint8_t *p=block+r*width;
#if defined(__aarch64__) && !defined(TIGHTARRAY_NO_NEON)
                for(;width-j>=16;j+=16) total+=vaddlvq_u8(vld1q_u8(p+j));
#endif
                for(;j<width;j++) total+=p[j];
                memcpy((uint8_t *)buffer.buf+8*(base+r),&total,8);
            }
        }
        PyBuffer_Release(&buffer); Py_RETURN_NONE;
    }
    if(outer.ndim==1 && inner.ndim==1 && outer.stride[0]==1 && outer.size>=8 && inner.size>=2 && (uintptr_t)buffer.buf%_Alignof(uint64_t)==0) {
        uint64_t *out=buffer.buf; memset(out,0,(size_t)buffer.len);
        uint8_t block[1024];
        for(Py_ssize_t row=0;row<inner.size;row++) {
            Py_ssize_t start=(Py_ssize_t)((__int128)v.offset+(__int128)row*inner.stride[0]);
            for(Py_ssize_t base=0;base<outer.size;base+=1024) {
                Py_ssize_t n=outer.size-base<1024?outer.size-base:1024;
                unpack_range(a,start+base,n,block);
                Py_ssize_t j=0;
#if defined(__aarch64__) && !defined(TIGHTARRAY_NO_NEON)
                for(;n-j>=8;j+=8) {
                    uint16x8_t x=vmovl_u8(vld1_u8(block+j));
                    uint32x4_t lo=vmovl_u16(vget_low_u16(x)),hi=vmovl_u16(vget_high_u16(x));
                    uint64_t *p=out+base+j;
                    vst1q_u64(p,vaddw_u32(vld1q_u64(p),vget_low_u32(lo)));
                    vst1q_u64(p+2,vaddw_u32(vld1q_u64(p+2),vget_high_u32(lo)));
                    vst1q_u64(p+4,vaddw_u32(vld1q_u64(p+4),vget_low_u32(hi)));
                    vst1q_u64(p+6,vaddw_u32(vld1q_u64(p+6),vget_high_u32(hi)));
                }
#endif
                for(;j<n;j++) out[base+j]+=block[j];
            }
        }
        PyBuffer_Release(&buffer); Py_RETURN_NONE;
    }
    /* memcpy also supports a writable buffer with unaligned address. */
    for(Py_ssize_t out=0;out<outer.size;out++) {
        uint64_t total=0;
        if(inner.size) {
            Py_ssize_t base=v.offset+view_position(&outer,out);
            if(!inner.ndim) total=a->read(a,base);
            else {
                Py_ssize_t d=inner.ndim-1,run=inner.shape[d],step=inner.stride[d];
                while(d>0 && inner.stride[d-1]==(__int128)step*run) run*=inner.shape[--d];
                for(Py_ssize_t i=0;i<inner.size;i+=run) total+=sum_stride_range(a,base+view_position(&inner,i),step,run);
            }
        }
        memcpy((uint8_t *)buffer.buf+8*out,&total,8);
    }
    PyBuffer_Release(&buffer); Py_RETURN_NONE;
bad:
    PyBuffer_Release(&buffer); return NULL;
}
