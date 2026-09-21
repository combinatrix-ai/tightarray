/* Experimental runs: ULEB128(count minus one), then one value byte. */
static PyObject *compressed_rle_encode(PyObject *module,PyObject *args) {
    PyObject *raw,*palette=NULL; Py_ssize_t limit;
    if(!PyArg_ParseTuple(args,"On|O:_rle_encode",&raw,&limit,&palette)) return NULL;
    if(!PyBytes_Check(raw)) { PyErr_SetString(PyExc_TypeError,"raw must be bytes"); return NULL; }
    uint16_t inverse[256];
    int translated=0;
    if(palette) {
        if(!PyBytes_Check(palette) || PyBytes_GET_SIZE(palette)>256) {
            PyErr_SetString(PyExc_TypeError,"palette must be bytes of length at most 256"); return NULL;
        }
        Py_ssize_t palette_size=PyBytes_GET_SIZE(palette);
        if(palette_size) {
            translated=1;
            for(unsigned i=0;i<256;i++) inverse[i]=256;
            const uint8_t *colors=(const uint8_t *)PyBytes_AS_STRING(palette);
            for(Py_ssize_t i=0;i<palette_size;i++) {
                if(inverse[colors[i]]!=256) { PyErr_SetString(PyExc_ValueError,"duplicate palette value"); return NULL; }
                inverse[colors[i]]=(uint16_t)i;
            }
        }
    }
    Py_ssize_t length=PyBytes_GET_SIZE(raw);
    if(limit<=0) Py_RETURN_NONE;
    if(!length) return PyBytes_FromStringAndSize("",0);
    if(limit<=2) Py_RETURN_NONE;
    if(length>PY_SSIZE_T_MAX/2) {
        PyErr_SetString(PyExc_OverflowError,"RLE maximum payload size overflow"); return NULL;
    }
    Py_ssize_t capacity=length*2;
    if(capacity>=limit) capacity=limit-1;
    PyObject *out=PyBytes_FromStringAndSize(NULL,capacity);
    if(!out) return NULL;
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
    Py_ssize_t used=0,index=0;
    while(index<length) {
        if(limit-used<=2 || capacity-used<2) { Py_DECREF(out); Py_RETURN_NONE; }
        Py_ssize_t count=1;
        while(count<length-index && src[index+count]==src[index]) count++;
        uint16_t value=translated?inverse[src[index]]:src[index];
        if(value==256) { Py_DECREF(out); PyErr_SetString(PyExc_ValueError,"run value outside palette"); return NULL; }
        size_t remaining=(size_t)(count-1), scan=remaining;
        Py_ssize_t record=2;
        while(scan>=128) { record++; scan>>=7; }
        if(record>=limit-used || record>capacity-used) { Py_DECREF(out); Py_RETURN_NONE; }
        while(remaining>=128) { dst[used++]=(uint8_t)((remaining&127)|128); remaining>>=7; }
        dst[used++]=(uint8_t)remaining; dst[used++]=(uint8_t)value;
        index+=count;
    }
    if(_PyBytes_Resize(&out,used)<0) return NULL;
    return out;
}

static int compressed_rle_record(const uint8_t *src,Py_ssize_t size,
                                 Py_ssize_t *position,Py_ssize_t *count,uint8_t *value) {
    size_t decoded=0; unsigned shift=0;
    for(;;) {
        if(*position>=size) { PyErr_SetString(PyExc_ValueError,"truncated RLE run length"); return -1; }
        unsigned byte=src[(*position)++], digit=byte&127;
        if(shift>=sizeof(size_t)*8 || (size_t)digit>((size_t)PY_SSIZE_T_MAX-1)>>shift) {
            PyErr_SetString(PyExc_ValueError,"RLE run length overflow"); return -1;
        }
        decoded|=(size_t)digit<<shift;
        if(!(byte&128)) break;
        shift+=7;
    }
    if(decoded>(size_t)PY_SSIZE_T_MAX-1) { PyErr_SetString(PyExc_ValueError,"RLE run length overflow"); return -1; }
    if(*position>=size) { PyErr_SetString(PyExc_ValueError,"missing RLE value"); return -1; }
    *count=(Py_ssize_t)decoded+1; *value=src[(*position)++]; return 0;
}
static PyObject *compressed_rle_decode(PyObject *module,PyObject *args) {
    PyObject *payload; Py_ssize_t length;
    if(!PyArg_ParseTuple(args,"On:_rle_decode",&payload,&length)) return NULL;
    if(!PyBytes_Check(payload)) { PyErr_SetString(PyExc_TypeError,"payload must be bytes"); return NULL; }
    if(length<0) { PyErr_SetString(PyExc_ValueError,"invalid RLE decoded length"); return NULL; }
    Py_ssize_t size=PyBytes_GET_SIZE(payload), position=0,total=0,count;
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(payload); uint8_t value;
    while(position<size) {
        if(compressed_rle_record(src,size,&position,&count,&value)<0) return NULL;
        if(count>length-total) { PyErr_SetString(PyExc_ValueError,"RLE decoded length mismatch"); return NULL; }
        total+=count;
    }
    if(total!=length) { PyErr_SetString(PyExc_ValueError,"RLE decoded length mismatch"); return NULL; }
    PyObject *out=PyBytes_FromStringAndSize(NULL,length);
    if(!out) return NULL;
    uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
    Py_ssize_t offset=0; position=0;
    while(position<size) {
        if(compressed_rle_record(src,size,&position,&count,&value)<0) { Py_DECREF(out); return NULL; }
        memset(dst+offset,value,(size_t)count); offset+=count;
    }
    return out;
}
