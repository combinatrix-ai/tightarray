/* Private helpers for adaptive chunk storage. These bytes use the native
 * little-endian dense packed format, not _wire.h's big-endian aligned format.
 * Keep the GIL while accessing input buffers and allocating owned storage. */
static PyObject *compressed_byte_palette(PyObject *module, PyObject *raw) {
    if(!PyBytes_Check(raw)) {
        PyErr_SetString(PyExc_TypeError,"raw must be bytes"); return NULL;
    }
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    Py_ssize_t length=PyBytes_GET_SIZE(raw);
    uint8_t seen[256]={0}, values[256];
    for(Py_ssize_t i=0;i<length;i++) seen[src[i]]=1;
    Py_ssize_t count=0;
    for(unsigned value=0;value<256;value++) if(seen[value]) values[count++]=(uint8_t)value;
    return PyBytes_FromStringAndSize((const char *)values,count);
}

static PyObject *array_from_packed_bytes(PyObject *cls, PyObject *args) {
    PyObject *raw; Py_ssize_t length, offset=0; int bits;
    if(!PyArg_ParseTuple(args,"Oni|n:_from_packed_bytes",&raw,&length,&bits,&offset)) return NULL;
    if(!PyBytes_Check(raw)) {
        PyErr_SetString(PyExc_TypeError,"raw must be bytes"); return NULL;
    }
    Py_ssize_t raw_length=PyBytes_GET_SIZE(raw);
    if(offset<0 || offset>raw_length) {
        PyErr_SetString(PyExc_ValueError,"packed byte offset out of range"); return NULL;
    }
    if(length<0 || bits<1 || bits>8) {
        PyErr_SetString(PyExc_ValueError,"invalid length or bit width"); return NULL;
    }
    if((size_t)length>(SIZE_MAX-63)/(unsigned)bits) {
        PyErr_SetString(PyExc_OverflowError,"packed bit length overflow"); return NULL;
    }
    size_t bit_length=(size_t)length*(unsigned)bits;
    size_t words=(bit_length+63)/64;
    if(words>(size_t)PY_SSIZE_T_MAX/8) {
        PyErr_SetString(PyExc_OverflowError,"packed byte length overflow"); return NULL;
    }
    Py_ssize_t bytes=(Py_ssize_t)(words*8);
    if(raw_length-offset!=bytes) {
        PyErr_SetString(PyExc_ValueError,"packed byte length mismatch"); return NULL;
    }
    Array *result=allocate_storage(length,(unsigned)bits,0,0);
    if(!result) return NULL;
    if(bytes) memcpy(result->data,PyBytes_AS_STRING(raw)+offset,(size_t)bytes);
    unsigned tail=(unsigned)(bit_length&63);
    if(tail) result->data[words-1]&=(UINT64_C(1)<<tail)-1;
    return (PyObject *)result;
}
