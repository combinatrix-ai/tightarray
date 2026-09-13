/* Experimental numeric sequence kernels. No biological alphabet assumptions. */
static PyObject *array_rolling_codes(Array *a, PyObject *args) {
    int k,base;
    if(!PyArg_ParseTuple(args,"ii:_rolling_codes",&k,&base)) return NULL;
    if(k<1 || base<2 || base>256) { PyErr_SetString(PyExc_ValueError,"invalid window or radix"); return NULL; }
    uint64_t power=1;
    for(int i=1;i<k;i++) {
        if(power>UINT64_MAX/(unsigned)base) { PyErr_SetString(PyExc_ValueError,"window exceeds uint64"); return NULL; }
        power*=base;
    }
    if(power>UINT64_MAX/(unsigned)base) { PyErr_SetString(PyExc_ValueError,"window exceeds uint64"); return NULL; }
    Py_ssize_t n=a->length>=k?a->length-k+1:0;
    if(n>PY_SSIZE_T_MAX/8) { PyErr_NoMemory(); return NULL; }
    PyObject *out=PyBytes_FromStringAndSize(NULL,n*8);
    if(!out) return NULL;
    uint64_t code=0,p=1;
    for(Py_ssize_t i=0;i<a->length;i++) {
        unsigned v=a->read(a,i);
        if(v>=(unsigned)base) { Py_DECREF(out); PyErr_SetString(PyExc_ValueError,"value outside radix"); return NULL; }
        if(i<k) { code+=v*p; if(i+1<k)p*=base; }
        else code=code/base+(uint64_t)v*power;
        if(i>=k-1) memcpy(PyBytes_AS_STRING(out)+(i-k+1)*8,&code,8);
    }
    return out;
}
static PyObject *array_hamming_rows(Array *a, PyObject *args) {
    Py_ssize_t width; int cutoff;
    if(!PyArg_ParseTuple(args,"ni:_hamming_rows",&width,&cutoff)) return NULL;
    size_t lanes=64/a->bits;
    if(width<=0 || width%lanes || a->length%width || !a->aligned || a->start%lanes || cutoff<0 || cutoff>254) {
        PyErr_SetString(PyExc_ValueError,"requires whole aligned rows and cutoff 0..254"); return NULL;
    }
    Py_ssize_t n=a->length/width;
    if(n && n>PY_SSIZE_T_MAX/n) { PyErr_NoMemory(); return NULL; }
    PyObject *out=PyBytes_FromStringAndSize(NULL,n*n);
    if(!out)return NULL;
    uint8_t *dest=(uint8_t *)PyBytes_AS_STRING(out);memset(dest,0,n*n);
    uint64_t low=0;
    for(unsigned j=0;j<lanes;j++)low|=UINT64_C(1)<<(j*a->bits);
    const uint64_t *data=a->data+a->start/lanes;size_t words=width/lanes;
    for(Py_ssize_t i=0;i<n;i++) for(Py_ssize_t j=i;j<n;j++) {
        size_t d=0;
        for(size_t w=0;w<words;w++) {
            uint64_t x=data[i*words+w]^data[j*words+w],fold=x;
            for(unsigned b=1;b<a->bits;b++)fold|=x>>b;
            d+=__builtin_popcountll(fold&low);
            if(d>(unsigned)cutoff)break;
        }
        if(d<=(unsigned)cutoff)dest[i*n+j]=dest[j*n+i]=(uint8_t)(d+1);
    }
    return out;
}
