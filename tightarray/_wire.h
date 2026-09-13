/* Experimental 64-bit big-endian, least-significant-lane-first codec.
 * Padding is kept separately so it cannot affect native reductions/equality. */
static uint64_t wire_mask(unsigned n) {
    return n == 64 ? UINT64_MAX : (UINT64_C(1) << n) - 1;
}
static uint64_t wire_load(const char *p) {
    uint64_t w; memcpy(&w,p,8); return __builtin_bswap64(w);
}
static void wire_store(char *p,uint64_t w) {
    w=__builtin_bswap64(w); memcpy(p,&w,8);
}
static PyObject *array_from_word_bytes(PyObject *cls, PyObject *args) {
    Py_buffer buf; Py_ssize_t length; int bits;
    if(!PyArg_ParseTuple(args,"y*ni:_from_word_bytes",&buf,&length,&bits)) return NULL;
    if(length<0 || bits<1 || bits>8) {
        PyBuffer_Release(&buf); PyErr_SetString(PyExc_ValueError,"invalid length or bit width"); return NULL;
    }
    size_t lanes=64/bits, words=(size_t)length/lanes+((size_t)length%lanes!=0);
    if(words>(size_t)PY_SSIZE_T_MAX/8 || buf.len!=(Py_ssize_t)(words*8)) {
        PyBuffer_Release(&buf); PyErr_SetString(PyExc_ValueError,"wire byte length mismatch"); return NULL;
    }
    Array *a=allocate(length,bits,1);
    if(!a) { PyBuffer_Release(&buf); return NULL; }
    PyObject *padding=NULL;
    for(size_t i=0;i<words;i++) {
        size_t remaining=(size_t)length-i*lanes;
        uint64_t mask=wire_mask((remaining<lanes?remaining:lanes)*bits);
        uint64_t w=wire_load((const char *)buf.buf+i*8), p=w&~mask;
        a->data[i]=w&mask;
        if(p && !padding) {
            padding=PyBytes_FromStringAndSize(NULL,buf.len);
            if(!padding) { Py_DECREF(a); PyBuffer_Release(&buf); return NULL; }
            memset(PyBytes_AS_STRING(padding),0,buf.len);
        }
        if(padding) wire_store(PyBytes_AS_STRING(padding)+i*8,p);
    }
    PyBuffer_Release(&buf);
    if(!padding) { padding=Py_None; Py_INCREF(padding); }
    return Py_BuildValue("NN",a,padding);
}
static PyObject *array_to_word_bytes(Array *a, PyObject *padding) {
    size_t lanes=64/a->bits, words=(size_t)a->length/lanes+((size_t)a->length%lanes!=0);
    if(words>(size_t)PY_SSIZE_T_MAX/8) { PyErr_NoMemory(); return NULL; }
    Py_ssize_t size=(Py_ssize_t)(words*8);
    if(padding!=Py_None && (!PyBytes_Check(padding) || PyBytes_GET_SIZE(padding)!=size)) {
        PyErr_SetString(PyExc_ValueError,"padding must be None or matching bytes"); return NULL;
    }
    PyObject *out=PyBytes_FromStringAndSize(NULL,size);
    if(!out) return NULL;
    const uint64_t *direct=(a->aligned && a->start%lanes==0)?a->data+a->start/lanes:NULL;
    for(size_t i=0;i<words;i++) {
        size_t pos=i*lanes, remaining=(size_t)a->length-pos;
        unsigned count=remaining<lanes?remaining:lanes;
        uint64_t mask=wire_mask(count*a->bits);
        uint64_t w=(direct?direct[i]:group(a,pos,a->bits,count))&mask;
        if(padding!=Py_None) w|=wire_load(PyBytes_AS_STRING(padding)+i*8)&~mask;
        wire_store(PyBytes_AS_STRING(out)+i*8,w);
    }
    return out;
}
