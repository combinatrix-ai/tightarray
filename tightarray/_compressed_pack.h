/* Packed byte payload construction without Array/exporter temporaries.
 * Every destination store is memcpy, so PyBytes alignment is irrelevant. */
#if defined(__aarch64__) && !defined(TIGHTARRAY_NO_NEON)
#define BYTE_PACK_VECTOR(B) \
    uint8x8_t invalid=vdup_n_u8(0); \
    if((B)==1 || (B)==2 || (B)==4) { \
        const int8_t shifts[16]={0,(B)%8,(2*(B))%8,(3*(B))%8,(4*(B))%8,(5*(B))%8,(6*(B))%8,(7*(B))%8,0,(B)%8,(2*(B))%8,(3*(B))%8,(4*(B))%8,(5*(B))%8,(6*(B))%8,(7*(B))%8}; \
        for(;length-i>=16;i+=16) { \
            uint8x16_t v=vld1q_u8(src+i); invalid=vorr_u8(invalid,vorr_u8(vget_low_u8(v),vget_high_u8(v))); \
            v=vshlq_u8(v,vld1q_s8(shifts)); v=vpaddq_u8(v,v); \
            if((B)<=2) v=vpaddq_u8(v,v); if((B)==1) v=vpaddq_u8(v,v); \
            uint64_t x=vgetq_lane_u64(vreinterpretq_u64_u8(v),0); \
            memcpy(dst+(size_t)i*(B)/8,&x,2*(B)); \
        } \
    } \
    for(;length-i>=8;i+=8) { \
        uint8x8_t v=vld1_u8(src+i); invalid=vorr_u8(invalid,v); \
        uint64_t x=compress##B(v); memcpy(dst+(size_t)i*(B)/8,&x,(B)); \
    } \
    invalid_bits|=vmaxv_u8(invalid);
#else
#define BYTE_PACK_VECTOR(B) \
    for(;length-i>=8;i+=8) { \
        uint64_t x=0; \
        for(unsigned j=0;j<8;j++) { invalid_bits|=src[i+j]; x|=(uint64_t)src[i+j]<<(j*(B)); } \
        memcpy(dst+(size_t)i*(B)/8,&x,(B)); \
    }
#endif
#define BYTE_PACK(B) \
static int compressed_pack##B(const uint8_t *src,Py_ssize_t length,uint8_t *dst,size_t bytes) { \
    Py_ssize_t i=0; unsigned invalid_bits=0; \
    BYTE_PACK_VECTOR(B) \
    size_t offset=(size_t)i*(B)/8; \
    if(i<length) { \
        uint64_t x=0; unsigned j=0; \
        for(;i<length;i++,j++) { invalid_bits|=src[i]; x|=(uint64_t)src[i]<<(j*(B)); } \
        size_t tail=(j*(B)+7)/8; memcpy(dst+offset,&x,tail); offset+=tail; \
    } \
    if(offset<bytes) memset(dst+offset,0,bytes-offset); \
    return (invalid_bits>>(B))?-1:0; \
}
BYTE_PACK(1) BYTE_PACK(2) BYTE_PACK(3) BYTE_PACK(4)
BYTE_PACK(5) BYTE_PACK(6) BYTE_PACK(7)
#undef BYTE_PACK
#undef BYTE_PACK_VECTOR
static int (*compressed_byte_packers[7])(const uint8_t *,Py_ssize_t,uint8_t *,size_t)={
    compressed_pack1,compressed_pack2,compressed_pack3,compressed_pack4,
    compressed_pack5,compressed_pack6,compressed_pack7
};
static PyObject *compressed_pack_bytes(PyObject *module,PyObject *args) {
    PyObject *raw,*width;
    if(!PyArg_ParseTuple(args,"OO:_pack_bytes",&raw,&width)) return NULL;
    if(!PyBytes_CheckExact(raw)) { PyErr_SetString(PyExc_TypeError,"raw must be exact bytes"); return NULL; }
    Py_ssize_t bits=PyNumber_AsSsize_t(width,PyExc_OverflowError);
    if(bits==-1 && PyErr_Occurred()) return NULL;
    if(bits<1 || bits>8) { PyErr_SetString(PyExc_ValueError,"bits must be between 1 and 8"); return NULL; }
    Py_ssize_t length=PyBytes_GET_SIZE(raw);
    if((size_t)length>(SIZE_MAX-63)/(size_t)bits) { PyErr_SetString(PyExc_OverflowError,"packed bit length overflow"); return NULL; }
    size_t bytes=(((size_t)length*(size_t)bits+63)/64)*8;
    if(bytes>(size_t)PY_SSIZE_T_MAX) { PyErr_SetString(PyExc_OverflowError,"packed byte length overflow"); return NULL; }
    if(bits==8 && bytes==(size_t)length) return Py_NewRef(raw);
    PyObject *out=PyBytes_FromStringAndSize(NULL,(Py_ssize_t)bytes);
    if(!out) return NULL;
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
    if(bits==8) {
        memcpy(dst,src,(size_t)length); memset(dst+length,0,bytes-(size_t)length);
    } else if(compressed_byte_packers[bits-1](src,length,dst,bytes)<0) {
        Py_DECREF(out); PyErr_SetString(PyExc_ValueError,"value outside bit width"); return NULL;
    }
    return out;
}
