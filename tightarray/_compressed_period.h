/* Shortest exact period <=256, with at least two periods of input.
 * KMP on at most512 bytes bounds scratch and candidate discovery. If an
 * eligible period q exists, the prefix has shortest period p<=q. For a512-byte
 * prefix Fine-Wilf applies to p,q<=256; minimality implies p divides q. Thus
 * a full q-periodic input also extends p, including a partial final period. */
static PyObject *compressed_byte_period(PyObject *module,PyObject *raw) {
    if(!PyBytes_Check(raw)) { PyErr_SetString(PyExc_TypeError,"raw must be bytes"); return NULL; }
    Py_ssize_t length=PyBytes_GET_SIZE(raw);
    if(length<2) return PyLong_FromLong(0);
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    unsigned sample=length<512?(unsigned)length:512;
    uint16_t prefix[512]={0};
    for(unsigned i=1;i<sample;i++) {
        unsigned matched=prefix[i-1];
        while(matched && src[i]!=src[matched]) matched=prefix[matched-1];
        if(src[i]==src[matched]) matched++;
        prefix[i]=(uint16_t)matched;
    }
    unsigned period=sample-prefix[sample-1];
    if(period>256 || (Py_ssize_t)period>length/2) return PyLong_FromLong(0);
    if(memcmp(src+period,src,(size_t)(length-period))) return PyLong_FromLong(0);
    return PyLong_FromUnsignedLong(period);
}
