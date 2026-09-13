/* Shared, validated logical view descriptor. Strides are in elements, not bits. */
#define VIEW_MAX_NDIM 64
typedef struct {
    Py_ssize_t ndim, size, offset, shape[VIEW_MAX_NDIM], stride[VIEW_MAX_NDIM];
    int contiguous;
} ArrayView;

static int parse_view(Array *a, PyObject *shape, PyObject *strides, Py_ssize_t offset, ArrayView *v) {
    PyObject *s=PySequence_Fast(shape,"shape must be a sequence");
    if(!s) return -1;
    PyObject *t=PySequence_Fast(strides,"strides must be a sequence");
    if(!t) { Py_DECREF(s); return -1; }
    v->ndim=PySequence_Fast_GET_SIZE(s); v->offset=offset; v->size=1; v->contiguous=1;
    if(v->ndim>VIEW_MAX_NDIM || PySequence_Fast_GET_SIZE(t)!=v->ndim) {
        PyErr_SetString(PyExc_ValueError,"invalid view dimensions"); goto bad;
    }
    int empty=0;
    for(Py_ssize_t d=0;d<v->ndim;d++) {
        v->shape[d]=PyLong_AsSsize_t(PySequence_Fast_GET_ITEM(s,d));
        if(PyErr_Occurred()) goto bad;
        v->stride[d]=PyLong_AsSsize_t(PySequence_Fast_GET_ITEM(t,d));
        if(PyErr_Occurred()) goto bad;
        if(v->shape[d]<0) { PyErr_SetString(PyExc_ValueError,"negative dimension"); goto bad; }
        if(!v->shape[d]) empty=1;
    }
    if(empty) { v->size=0; Py_DECREF(s); Py_DECREF(t); return 0; }
    __int128 low=offset,high=offset,expected=1;
    for(Py_ssize_t d=v->ndim;d-->0;) {
        if(v->shape[d]>1 && v->stride[d]!=expected) v->contiguous=0;
        expected*=v->shape[d];
        if(expected>PY_SSIZE_T_MAX) { PyErr_SetString(PyExc_OverflowError,"view size overflow"); goto bad; }
        __int128 span=(__int128)(v->shape[d]-1)*v->stride[d];
        if(span<0) low+=span; else high+=span;
    }
    v->size=(Py_ssize_t)expected;
    if(low<0 || high>=a->length) { PyErr_SetString(PyExc_IndexError,"view exceeds storage"); goto bad; }
    Py_DECREF(s); Py_DECREF(t); return 0;
bad:
    Py_DECREF(s); Py_DECREF(t); return -1;
}

static Py_ssize_t view_position(const ArrayView *v, Py_ssize_t index) {
    __int128 pos=v->offset;
    for(Py_ssize_t d=v->ndim;d-->0;) {
        pos+=(__int128)(index%v->shape[d])*v->stride[d]; index/=v->shape[d];
    }
    return (Py_ssize_t)pos;
}

static void unpack_range(const Array *a,Py_ssize_t offset,Py_ssize_t n,uint8_t *out) {
    Array span=*a; span.start+=offset; span.length=n;
    if(a->bits==8) memcpy(out,(uint8_t *)a->data+span.start,n);
    else unpackers[a->bits-1](&span,out);
}

/* Fold adjacent base-2^B digits inside each word; no decoded byte array. */
#define SUM_KERNEL(B) \
static inline uint64_t sum_word##B(uint64_t x) { \
    x &= UINT64_MAX >> (64-(64/(B))*(B)); \
    for(unsigned width=(B);width<64;width*=2) { \
        uint64_t mask=0; \
        for(unsigned pos=0;pos<64;pos+=2*width) mask|=((1ull<<width)-1)<<pos; \
        x=(x&mask)+((x>>width)&mask); \
    } \
    return x; \
} \
static uint64_t sum_packed##B(const Array *a,Py_ssize_t offset,Py_ssize_t n) { \
    const unsigned lanes=64/(B); \
    uint64_t total=0; Py_ssize_t i=0; \
    if(a->aligned || 64%(B)==0) { \
        while(i<n && (a->start+offset+i)%lanes) { total+=a->aligned?a##B(a,offset+i):p##B(a,offset+i); i++; } \
        size_t word=(a->start+offset+i)/lanes; \
        for(;n-i>=lanes;i+=lanes,word++) total+=sum_word##B(a->data[word]); \
    } else { \
        if((B)>=5) { \
            while(i<n && (a->start+offset+i)%8) { total+=p##B(a,offset+i); i++; } \
            for(;n-i>=(64+(B)-1)/(B);i+=8) { \
                uint64_t x; memcpy(&x,(const uint8_t *)a->data+(a->start+offset+i)*(B)/8,8); \
                x &= UINT64_MAX >> (64-8*(B)); \
                total+=sum_word##B(x); \
            } \
        } \
        for(;n-i>=lanes;i+=lanes) total+=sum_word##B(group(a,offset+i,B,lanes)); \
    } \
    for(;i<n;i++) total+=a->aligned?a##B(a,offset+i):p##B(a,offset+i); \
    return total; \
} \
static uint64_t sum_strided##B(const Array *a,Py_ssize_t offset,Py_ssize_t stride,Py_ssize_t n) { \
    uint64_t total=0; size_t pos=offset; Py_ssize_t i=0; \
    if(stride>1 && stride<=(64/(B)-1)/3 && n>=32) { \
        unsigned take=1+(64/(B)-1)/(unsigned)stride, span=(take-1)*(unsigned)stride+1; \
        uint64_t mask=0; for(unsigned j=0;j<take;j++) mask|=((1ull<<(B))-1)<<(j*stride*(B)); \
        for(;n-i>=take;i+=take,pos+=take*(size_t)stride) { \
            uint64_t x=group(a,pos,B,span)&mask; \
            total+=(B)==1?(uint64_t)__builtin_popcountll(x):sum_word##B(x); \
        } \
    } \
    if(a->aligned) for(;i<n;i++,pos+=(size_t)stride) total+=a##B(a,pos); \
    else for(;i<n;i++,pos+=(size_t)stride) total+=p##B(a,pos); \
    return total; \
}
SUM_KERNEL(1) SUM_KERNEL(2) SUM_KERNEL(3) SUM_KERNEL(4)
SUM_KERNEL(5) SUM_KERNEL(6) SUM_KERNEL(7) SUM_KERNEL(8)
#undef SUM_KERNEL
static uint64_t (*packed_sums[8])(const Array *,Py_ssize_t,Py_ssize_t)={sum_packed1,sum_packed2,sum_packed3,sum_packed4,sum_packed5,sum_packed6,sum_packed7,sum_packed8};
static uint64_t (*strided_sums[8])(const Array *,Py_ssize_t,Py_ssize_t,Py_ssize_t)={sum_strided1,sum_strided2,sum_strided3,sum_strided4,sum_strided5,sum_strided6,sum_strided7,sum_strided8};

/* Small fixed strides over byte-aligned packed groups. */
#define SPARSE_BYTES(B,S) \
static uint64_t sum_bytes##B##_##S(const Array *a,Py_ssize_t offset,Py_ssize_t n) { \
    uint64_t masks[S]={0},total=0; \
    for(unsigned j=0;j<(S);j++) for(unsigned k=0;k<8;k++) if((j*8+k)%(S)==0) masks[j]|=((1ull<<(B))-1)<<(k*(B)); \
    Py_ssize_t i=0; const uint8_t *src=(const uint8_t *)a->data+(a->start+offset)*(B)/8; \
    for(;n-i>=32;i+=8,src+=(S)*(B)) { \
        for(unsigned j=0;j<(S);j++) { uint64_t x; memcpy(&x,src+j*(B),8); total+=sum_word##B(x&masks[j]); } \
    } \
    for(;i<n;i++) total+=p##B(a,offset+i*(S)); \
    return total; \
}
#define SPARSE_WIDTH(B) SPARSE_BYTES(B,2) SPARSE_BYTES(B,3) SPARSE_BYTES(B,4)
SPARSE_WIDTH(3) SPARSE_WIDTH(4) SPARSE_WIDTH(5) SPARSE_WIDTH(6) SPARSE_WIDTH(7) SPARSE_WIDTH(8)
#undef SPARSE_WIDTH
#undef SPARSE_BYTES
static uint64_t (*byte_sums[6][3])(const Array *,Py_ssize_t,Py_ssize_t)={
 {sum_bytes3_2,sum_bytes3_3,sum_bytes3_4},{sum_bytes4_2,sum_bytes4_3,sum_bytes4_4},
 {sum_bytes5_2,sum_bytes5_3,sum_bytes5_4},{sum_bytes6_2,sum_bytes6_3,sum_bytes6_4},
 {sum_bytes7_2,sum_bytes7_3,sum_bytes7_4},{sum_bytes8_2,sum_bytes8_3,sum_bytes8_4}};

#define SPARSE_ALIGNED(B,S) \
static uint64_t sum_aligned##B##_##S(const Array *a,Py_ssize_t offset,Py_ssize_t n) { \
    const unsigned lanes=64/(B); uint64_t masks[S]={0},total=0; \
    for(unsigned j=0;j<(S);j++) for(unsigned k=0;k<lanes;k++) if((j*lanes+k)%(S)==0) masks[j]|=((1ull<<(B))-1)<<(k*(B)); \
    Py_ssize_t i=0; const uint64_t *src=a->data+(a->start+offset)/lanes; \
    for(;n-i>=lanes;i+=lanes,src+=(S)) for(unsigned j=0;j<(S);j++) total+=sum_word##B(src[j]&masks[j]); \
    for(;i<n;i++) total+=a##B(a,offset+i*(S)); \
    return total; \
}
#define ALIGNED_WIDTH(B) SPARSE_ALIGNED(B,2) SPARSE_ALIGNED(B,3) SPARSE_ALIGNED(B,4)
ALIGNED_WIDTH(3) ALIGNED_WIDTH(5) ALIGNED_WIDTH(6) ALIGNED_WIDTH(7)
#undef ALIGNED_WIDTH
#undef SPARSE_ALIGNED
static uint64_t (*aligned_sparse[8][3])(const Array *,Py_ssize_t,Py_ssize_t)={
 {NULL,NULL,NULL},{NULL,NULL,NULL},{sum_aligned3_2,sum_aligned3_3,sum_aligned3_4},{NULL,NULL,NULL},
 {sum_aligned5_2,sum_aligned5_3,sum_aligned5_4},{sum_aligned6_2,sum_aligned6_3,sum_aligned6_4},
 {sum_aligned7_2,sum_aligned7_3,sum_aligned7_4},{NULL,NULL,NULL}};

static uint64_t sum_range(const Array *a,Py_ssize_t offset,Py_ssize_t n) {
    uint64_t total=0;
    if(a->bits==1) {
        Array span=*a; span.start+=offset; span.length=n;
        return count1(&span,1);
    }
    if(a->bits<8) return packed_sums[a->bits-1](a,offset,n);
    const uint8_t *values=(const uint8_t *)a->data+a->start+offset;
    Py_ssize_t i=0;
#if defined(__aarch64__) && !defined(TIGHTARRAY_NO_NEON)
    for(;n-i>=16;i+=16) total+=vaddlvq_u8(vld1q_u8(values+i));
#endif
    for(;i<n;i++) total+=values[i];
    return total;
}

static uint64_t sum_stride_range(const Array *a,Py_ssize_t offset,Py_ssize_t stride,Py_ssize_t n) {
    if(!n) return 0;
    if(n==1) return a->read(a,offset);
    if(!stride) return (uint64_t)n*a->read(a,offset);
    if(stride<0) { offset=(Py_ssize_t)((__int128)offset+(n-1)*(__int128)stride); stride=-stride; }
    if(a->aligned && stride>=2 && stride<=4 && n>=128 && aligned_sparse[a->bits-1][stride-2] && (a->start+offset)%(64/a->bits)==0)
        return aligned_sparse[a->bits-1][stride-2](a,offset,n);
    if(a->bits>=3 && stride>=2 && stride<=4 && n>=128 && (!a->aligned || 64%a->bits==0) && (a->start+offset)%8==0)
        return byte_sums[a->bits-3][stride-2](a,offset,n);
    return stride==1?sum_range(a,offset,n):strided_sums[a->bits-1](a,offset,stride,n);
}

static PyObject *array_sum(Array *a,PyObject *unused) {
    return PyLong_FromUnsignedLongLong(sum_range(a,0,a->length));
}
static PyObject *array_view_bytes(Array *a,PyObject *args) {
    PyObject *shape,*strides; Py_ssize_t offset; ArrayView v;
    if(!PyArg_ParseTuple(args,"OOn",&shape,&strides,&offset) || parse_view(a,shape,strides,offset,&v)<0) return NULL;
    PyObject *out=PyBytes_FromStringAndSize(NULL,v.size); if(!out) return NULL;
    uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
    if(v.size && v.contiguous) unpack_range(a,v.offset,v.size,dst);
    else for(Py_ssize_t i=0;i<v.size;i++) dst[i]=a->read(a,view_position(&v,i));
    return out;
}
static PyObject *array_view_sum(Array *a,PyObject *args) {
    PyObject *shape,*strides; Py_ssize_t offset; ArrayView v;
    if(!PyArg_ParseTuple(args,"OOn",&shape,&strides,&offset) || parse_view(a,shape,strides,offset,&v)<0) return NULL;
    uint64_t total=0;
    if(v.size && v.contiguous) total=sum_range(a,v.offset,v.size);
    else if(v.size && v.ndim==1) total=sum_stride_range(a,v.offset,v.stride[0],v.size);
    else if(v.size) {
        /* Walk outer dimensions once per inner run, not once per element. */
        Py_ssize_t d=v.ndim-1, length=v.shape[d], stride=v.stride[d];
        while(d>0 && v.stride[d-1]==(__int128)stride*length) length*=v.shape[--d];
        for(Py_ssize_t i=0;i<v.size;i+=length) {
            Py_ssize_t pos=view_position(&v,i);
            total+=stride==1?sum_range(a,pos,length):sum_stride_range(a,pos,stride,length);
        }
    }
    return PyLong_FromUnsignedLongLong(total);
}
static PyObject *array_view_assign(Array *a,PyObject *args) {
    PyObject *shape,*strides; Py_ssize_t offset; ArrayView v; Py_buffer input;
    if(!PyArg_ParseTuple(args,"OOny*",&shape,&strides,&offset,&input)) return NULL;
    if(parse_view(a,shape,strides,offset,&v)<0) { PyBuffer_Release(&input); return NULL; }
    if(input.len!=v.size) { PyErr_SetString(PyExc_ValueError,"assignment size mismatch"); goto bad; }
    const uint8_t *values=input.buf;
    for(Py_ssize_t i=0;i<v.size;i++) if(values[i]>=(1u<<a->bits)) {
        PyErr_SetString(PyExc_ValueError,"assignment exceeds storage width"); goto bad;
    }
    /* Validate all values first: failure never leaves partially mutated storage. */
    for(Py_ssize_t i=0;i<v.size;i++) put(a,v.contiguous?v.offset+i:view_position(&v,i),values[i]);
    PyBuffer_Release(&input); Py_RETURN_NONE;
bad:
    PyBuffer_Release(&input); return NULL;
}
