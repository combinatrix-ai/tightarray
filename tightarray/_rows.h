/* Included after the Array implementation; no per-row Python objects retained. */
typedef struct { PyObject_HEAD Array *data; Py_ssize_t rows,cols; size_t *offsets; } Rows;
static PyTypeObject RowsType;
static int ready(Rows *r) { if(r->data) return 1; PyErr_SetString(PyExc_RuntimeError,"uninitialized container"); return 0; }
static size_t row_start(Rows *r,Py_ssize_t i) { return r->offsets?r->offsets[i]:(size_t)i*r->cols; }
static int row_index(Rows *r,Py_ssize_t *i) {
    if(*i<0) *i+=r->rows;
    if(*i<0 || *i>=r->rows) { PyErr_SetString(PyExc_IndexError,"row index out of range"); return -1; } return 0;
}
static int rows_init(Rows *r,PyObject *args,PyObject *kwargs) {
    if(r->data) { PyErr_SetString(PyExc_RuntimeError,"container cannot be reinitialized"); return -1; }
    Array *data; Py_ssize_t rows,cols; PyObject *offsets=Py_None;
    static char *names[]={"data","rows","cols","offsets",NULL};
    if(!PyArg_ParseTupleAndKeywords(args,kwargs,"O!nn|O",names,&ArrayType,&data,&rows,&cols,&offsets)) return -1;
    if(rows<0 || cols<0 || rows==PY_SSIZE_T_MAX || (size_t)(rows+1)>SIZE_MAX/sizeof(size_t)) { PyErr_SetString(PyExc_ValueError,"invalid shape"); return -1; }
    size_t *owned=NULL;
    if(offsets!=Py_None) {
        PyObject *seq=PySequence_Tuple(offsets); if(!seq) return -1;
        if(PySequence_Fast_GET_SIZE(seq)!=rows+1) { Py_DECREF(seq); PyErr_SetString(PyExc_ValueError,"offsets length mismatch"); return -1; }
        owned=PyMem_Malloc((rows+1)*sizeof(size_t)); if(!owned) { Py_DECREF(seq); PyErr_NoMemory(); return -1; }
        for(Py_ssize_t i=0;i<=rows;i++) {
            Py_ssize_t v=PyNumber_AsSsize_t(PySequence_Fast_GET_ITEM(seq,i),PyExc_OverflowError);
            if((v==-1 && PyErr_Occurred()) || v<0 || v>data->length || (!i && v) || (i && (size_t)v<owned[i-1])) {
                if(!PyErr_Occurred()) PyErr_SetString(PyExc_ValueError,"invalid offsets");
                PyMem_Free(owned); Py_DECREF(seq); return -1;
            } owned[i]=v;
        }
        Py_DECREF(seq);
        if(owned[rows]!=(size_t)data->length) { PyMem_Free(owned); PyErr_SetString(PyExc_ValueError,"offsets must cover data"); return -1; }
    } else if((cols && rows>PY_SSIZE_T_MAX/cols) || rows*cols!=data->length) { PyErr_SetString(PyExc_ValueError,"shape does not match data length"); return -1; }
    Py_INCREF(data); Py_XDECREF(r->data); PyMem_Free(r->offsets);
    r->data=data; r->rows=rows; r->cols=cols; r->offsets=owned; return 0;
}
static void rows_dealloc(Rows *r) { Py_XDECREF(r->data); PyMem_Free(r->offsets); Py_TYPE(r)->tp_free((PyObject *)r); }
static Py_ssize_t rows_len(Rows *r) { return ready(r)?r->rows:-1; }
static PyObject *rows_item(Rows *r,Py_ssize_t i) {
    if(!ready(r) || row_index(r,&i)<0) return NULL;
    size_t start=row_start(r,i); return (PyObject *)view(r->data,start,row_start(r,i+1)-start);
}
static int rows_position(Rows *r,PyObject *key,Py_ssize_t *out) {
    if(PyTuple_GET_SIZE(key)!=2) { PyErr_SetString(PyExc_IndexError,"expected two indices"); return -1; }
    Py_ssize_t row=PyNumber_AsSsize_t(PyTuple_GET_ITEM(key,0),PyExc_IndexError);
    if((row==-1 && PyErr_Occurred()) || row_index(r,&row)<0) return -1;
    Py_ssize_t col=PyNumber_AsSsize_t(PyTuple_GET_ITEM(key,1),PyExc_IndexError);
    if(col==-1 && PyErr_Occurred()) return -1;
    size_t start=row_start(r,row); Py_ssize_t length=row_start(r,row+1)-start;
    if(col<0) col+=length;
    if(col<0 || col>=length) { PyErr_SetString(PyExc_IndexError,"column index out of range"); return -1; }
    *out=start+col; return 0;
}
static Rows *rows_empty_like(Rows *r,Py_ssize_t n) {
    Rows *out=(Rows *)Py_TYPE(r)->tp_alloc(Py_TYPE(r),0); if(!out) return NULL;
    out->rows=n; out->cols=r->cols;
    if(r->offsets) {
        out->offsets=PyMem_Calloc(n+1,sizeof(size_t));
        if(!out->offsets) { Py_DECREF(out); PyErr_NoMemory(); return NULL; }
    } return out;
}
static PyObject *rows_subscript(Rows *r,PyObject *key) {
    if(!ready(r)) return NULL;
    if(PyTuple_Check(key)) { Py_ssize_t i; if(rows_position(r,key,&i)<0) return NULL; return PyLong_FromLong(r->data->read(r->data,i)); }
    if(PyIndex_Check(key)) { Py_ssize_t i=PyNumber_AsSsize_t(key,PyExc_IndexError); if(i==-1 && PyErr_Occurred()) return NULL; return rows_item(r,i); }
    if(PySlice_Check(key)) {
        Py_ssize_t start,stop,step; if(PySlice_Unpack(key,&start,&stop,&step)<0) return NULL;
        Py_ssize_t n=PySlice_AdjustIndices(r->rows,&start,&stop,step);
        Rows *out=rows_empty_like(r,n); if(!out) return NULL;
        if(step==1) {
            size_t base=row_start(r,start),end=row_start(r,start+n);
            out->data=view(r->data,base,end-base);
            if(out->offsets) for(Py_ssize_t i=0;i<=n;i++) out->offsets[i]=row_start(r,start+i)-base;
        } else {
            size_t total=0;
            for(Py_ssize_t j=0,i=start;j<n;j++) { total+=row_start(r,i+1)-row_start(r,i); if(out->offsets) out->offsets[j+1]=total; if(j+1<n) i+=step; }
            out->data=allocate(total,r->data->bits,r->data->aligned);
            if(out->data) {
                size_t dest=0;
                for(Py_ssize_t j=0,i=start;j<n;j++) {
                    size_t end=row_start(r,i+1);
                    for(size_t k=row_start(r,i);k<end;k++) put(out->data,dest++,r->data->read(r->data,k));
                    if(j+1<n) i+=step;
                }
            }
        }
        if(!out->data) { Py_DECREF(out); return NULL; } return (PyObject *)out;
    } PyErr_SetString(PyExc_TypeError,"expected integer, slice, or pair of integers"); return NULL;
}
static int rows_assign(Rows *r,PyObject *key,PyObject *value) {
    if(!ready(r)) return -1;
    if(!value || !PyTuple_Check(key)) { PyErr_SetString(PyExc_TypeError,"assignment requires two scalar indices"); return -1; }
    Py_ssize_t i; uint8_t v;
    if(rows_position(r,key,&i)<0 || value_of(value,r->data->bits,&v)<0) return -1;
    put(r->data,i,v); return 0;
}
static PyObject *rows_copy(Rows *r,PyObject *unused) {
    if(!ready(r)) return NULL;
    Rows *out=rows_empty_like(r,r->rows); if(!out) return NULL;
    out->data=(Array *)array_copy(r->data,NULL); if(!out->data) { Py_DECREF(out); return NULL; }
    if(r->offsets) memcpy(out->offsets,r->offsets,(r->rows+1)*sizeof(size_t)); return (PyObject *)out;
}
static PyObject *rows_list(Rows *r,PyObject *unused) {
    if(!ready(r)) return NULL;
    PyObject *out=PyList_New(r->rows); if(!out) return NULL;
    for(Py_ssize_t i=0;i<r->rows;i++) {
        Array *v=(Array *)rows_item(r,i); if(!v) { Py_DECREF(out); return NULL; }
        PyObject *row=array_list(v,NULL); Py_DECREF(v);
        if(!row) { Py_DECREF(out); return NULL; } PyList_SET_ITEM(out,i,row);
    } return out;
}
static PyObject *rows_count(Rows *r,PyObject *v) { return ready(r)?array_count(r->data,v):NULL; }
static PyObject *rows_compare(PyObject *left,PyObject *right,int op) {
    if(!PyObject_TypeCheck(right,&RowsType) || (op!=Py_EQ && op!=Py_NE)) Py_RETURN_NOTIMPLEMENTED;
    Rows *a=(Rows *)left,*b=(Rows *)right; if(!ready(a)||!ready(b)) return NULL;
    int equal=a->rows==b->rows && a->cols==b->cols && !!a->offsets==!!b->offsets;
    if(equal && a->offsets) equal=memcmp(a->offsets,b->offsets,(a->rows+1)*sizeof(size_t))==0;
    if(!equal) return PyBool_FromLong(op==Py_NE);
    return array_compare((PyObject *)a->data,(PyObject *)b->data,op);
}
static PyObject *rows_sizeof(Rows *r,PyObject *unused) {
    size_t n=Py_TYPE(r)->tp_basicsize;
    if(r->data) {
        Array *a=r->data; n+=sizeof(Array)+(a->owner?0:(a->words?a->words:1)*8);
        if(a->owner) { a=(Array *)a->owner; n+=sizeof(Array)+(a->words?a->words:1)*8; }
    }
    if(r->offsets) n+=(r->rows+1)*sizeof(size_t); return PyLong_FromSize_t(n);
}
static PyObject *rows_shape(Rows *r,void *c) { if(!ready(r)) return NULL; return r->offsets?Py_BuildValue("nO",r->rows,Py_None):Py_BuildValue("nn",r->rows,r->cols); }
static PyObject *rows_bits(Rows *r,void *c) { return ready(r)?get_bits(r->data,NULL):NULL; }
static PyObject *rows_layout(Rows *r,void *c) { return ready(r)?get_layout(r->data,NULL):NULL; }
static PyObject *rows_nbytes(Rows *r,void *c) {
    if(!ready(r)) return NULL;
    return PyLong_FromSize_t((r->data->owner?0:(r->data->words?r->data->words:1)*8)+(r->offsets?(r->rows+1)*sizeof(size_t):0));
}
static PyObject *rows_equals(Rows *r,PyObject *other) {
    if(!PyObject_TypeCheck(other,&RowsType)) Py_RETURN_FALSE;
    return rows_compare((PyObject *)r,other,Py_EQ);
}
static PyObject *rows_bytes(Rows *r,PyObject *unused) { return ready(r)?array_bytes(r->data,NULL):NULL; }
static PyMethodDef rows_methods[]={
    {"equals",(PyCFunction)rows_equals,METH_O,"Whole-container value equality."},
    {"tobytes",(PyCFunction)rows_bytes,METH_NOARGS,"Flattened unpacked bytes."},
    {"copy",(PyCFunction)rows_copy,METH_NOARGS,"Independent copy."},{"tolist",(PyCFunction)rows_list,METH_NOARGS,"Nested lists."},
    {"count",(PyCFunction)rows_count,METH_O,"Count across rows."},{"__sizeof__",(PyCFunction)rows_sizeof,METH_NOARGS,"Total retained native memory."},{NULL,NULL,0,NULL}
};
static PyGetSetDef rows_getters[]={
    {"shape",(getter)rows_shape,NULL,NULL,NULL},{"bits",(getter)rows_bits,NULL,NULL,NULL},
    {"layout",(getter)rows_layout,NULL,NULL,NULL},{"nbytes",(getter)rows_nbytes,NULL,NULL,NULL},{NULL,NULL,NULL,NULL,NULL}
};
static PySequenceMethods rows_sequence={.sq_length=(lenfunc)rows_len,.sq_item=(ssizeargfunc)rows_item};
static PyMappingMethods rows_mapping={.mp_length=(lenfunc)rows_len,.mp_subscript=(binaryfunc)rows_subscript,.mp_ass_subscript=(objobjargproc)rows_assign};
static PyTypeObject RowsType={
    PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="tightarray._core._Rows",.tp_basicsize=sizeof(Rows),.tp_dealloc=(destructor)rows_dealloc,
    .tp_flags=Py_TPFLAGS_DEFAULT|Py_TPFLAGS_BASETYPE,.tp_new=PyType_GenericNew,.tp_init=(initproc)rows_init,
    .tp_as_sequence=&rows_sequence,.tp_as_mapping=&rows_mapping,.tp_methods=rows_methods,.tp_getset=rows_getters,
    .tp_richcompare=rows_compare,.tp_hash=PyObject_HashNotImplemented
};
