/* Exact modal default and the minimal nondefault span. Ties choose lowest byte.
 * Uniform and empty inputs use an empty span (0,0); empty default is zero.
 * Every counter is at most input length, so Py_ssize_t increments cannot wrap. */
static PyObject *compressed_byte_trim(PyObject *module,PyObject *raw) {
    if(!PyBytes_Check(raw)) { PyErr_SetString(PyExc_TypeError,"raw must be bytes"); return NULL; }
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    Py_ssize_t length=PyBytes_GET_SIZE(raw), counts[256]={0};
    for(Py_ssize_t i=0;i<length;i++) counts[src[i]]++;
    unsigned mode=0;
    for(unsigned value=1;value<256;value++) if(counts[value]>counts[mode]) mode=value;
    Py_ssize_t first=0,last=length;
    while(first<length && src[first]==mode) first++;
    if(first==length) first=last=0;
    else while(last>first && src[last-1]==mode) last--;
    return Py_BuildValue("inn",(int)mode,first,last);
}

/* Any default different from both endpoints omits no edge and cannot beat
 * the corresponding untrimmed representation with its smaller header.
 * Enumerate only the endpoint defaults; selection still compares full cost. */
static PyObject *compressed_byte_edge_spans(PyObject *module,PyObject *raw) {
    if(!PyBytes_Check(raw)) { PyErr_SetString(PyExc_TypeError,"raw must be bytes"); return NULL; }
    Py_ssize_t length=PyBytes_GET_SIZE(raw);
    if(!length) return PyTuple_New(0);
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    unsigned left=src[0],right=src[length-1];
    Py_ssize_t first=1;
    while(first<length && src[first]==left) first++;
    if(first==length) return Py_BuildValue("((inn))",(int)left,(Py_ssize_t)0,(Py_ssize_t)0);
    Py_ssize_t last=length-1;
    while(last>0 && src[last-1]==right) last--;
    if(left==right) return Py_BuildValue("((inn))",(int)left,first,last);
    return Py_BuildValue("((inn)(inn))",(int)left,first,length,(int)right,(Py_ssize_t)0,last);
}
