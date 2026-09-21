/* Native default-filled cache entry with a packed interior. Exact references
 * cannot form cycles. Bounds validate by subtraction before computing span end. */
typedef struct {
    PyObject_HEAD
    Array *data;
    PyObject *palette;
    Py_ssize_t start,length;
    uint8_t value;
    int dirty;
} CompressedSpanHot;
static PyObject *span_hot_new(PyTypeObject *type,PyObject *args,PyObject *kwargs) {
    PyObject *data,*palette=NULL,*value=NULL,*start=NULL,*length=NULL;
    static char *names[]={"data","palette","default","start","length",NULL};
    if(!PyArg_ParseTupleAndKeywords(args,kwargs,"O|O$OOO:_SpanHot",names,&data,&palette,&value,&start,&length)) return NULL;
    if(!value || !start || !length) { PyErr_SetString(PyExc_TypeError,"default, start and length are required"); return NULL; }
    if(!Py_IS_TYPE(data,&ArrayType)) { PyErr_SetString(PyExc_TypeError,"data must be an exact Array"); return NULL; }
    if(palette && (!PyBytes_CheckExact(palette) || PyBytes_GET_SIZE(palette)>256)) {
        PyErr_SetString(PyExc_TypeError,"palette must be exact bytes of length at most 256"); return NULL;
    }
    uint8_t fill;
    if(value_of(value,8,&fill)<0) return NULL;
    Py_ssize_t first=PyNumber_AsSsize_t(start,PyExc_OverflowError);
    if(first==-1 && PyErr_Occurred()) return NULL;
    Py_ssize_t size=PyNumber_AsSsize_t(length,PyExc_OverflowError);
    if(size==-1 && PyErr_Occurred()) return NULL;
    if(first<0 || size<0 || first>size || ((Array *)data)->length>size-first) {
        PyErr_SetString(PyExc_ValueError,"packed span must fit logical length"); return NULL;
    }
    CompressedSpanHot *hot=PyObject_New(CompressedSpanHot,type);
    if(!hot) return NULL;
    hot->data=(Array *)data; Py_INCREF(data);
    if(palette) { hot->palette=palette; Py_INCREF(palette); }
    else hot->palette=PyBytes_FromStringAndSize("",0);
    if(!hot->palette) { Py_DECREF(data); PyObject_Del(hot); return NULL; }
    hot->start=first; hot->length=size; hot->value=fill; hot->dirty=0;
    return (PyObject *)hot;
}
static void span_hot_dealloc(CompressedSpanHot *hot) {
    Py_DECREF(hot->data); Py_DECREF(hot->palette); PyObject_Del(hot);
}
static PyObject *span_hot_data(CompressedSpanHot *hot,void *unused) { Py_INCREF(hot->data); return (PyObject *)hot->data; }
static PyObject *span_hot_palette(CompressedSpanHot *hot,void *unused) { Py_INCREF(hot->palette); return hot->palette; }
static PyObject *span_hot_default(CompressedSpanHot *hot,void *unused) { return PyLong_FromLong(hot->value); }
static PyObject *span_hot_start(CompressedSpanHot *hot,void *unused) { return PyLong_FromSsize_t(hot->start); }
static PyObject *span_hot_length(CompressedSpanHot *hot,void *unused) { return PyLong_FromSsize_t(hot->length); }
static PyObject *span_hot_repeated(CompressedSpanHot *hot,void *unused) { Py_RETURN_TRUE; }
static PyObject *span_hot_dirty(CompressedSpanHot *hot,void *unused) { return PyBool_FromLong(hot->dirty); }
static int span_hot_set_dirty(CompressedSpanHot *hot,PyObject *value,void *unused) {
    if(!value || !PyBool_Check(value)) { PyErr_SetString(PyExc_TypeError,"dirty must be bool"); return -1; }
    hot->dirty=value==Py_True; return 0;
}
static PyObject *span_hot_nbytes(CompressedSpanHot *hot,void *unused) {
    Array *data=hot->data;
    size_t bytes=data->owner?0:(data->words?data->words:1)*8;
    return PyLong_FromSize_t(bytes+(size_t)PyBytes_GET_SIZE(hot->palette));
}
static PyObject *span_hot_item(CompressedSpanHot *hot,PyObject *key) {
    if(!PyIndex_Check(key)) { PyErr_SetString(PyExc_TypeError,"index must be an integer"); return NULL; }
    Py_ssize_t index=PyNumber_AsSsize_t(key,PyExc_IndexError);
    if(index==-1 && PyErr_Occurred()) return NULL;
    if(index<0) index+=hot->length;
    if(index<0 || index>=hot->length) { PyErr_SetString(PyExc_IndexError,"cache index out of range"); return NULL; }
    uint8_t value=hot->value;
    if(index>=hot->start && index-hot->start<hot->data->length) {
        value=hot->data->read(hot->data,(size_t)(index-hot->start));
        Py_ssize_t count=PyBytes_GET_SIZE(hot->palette);
        if(count) {
            if(value>=count) { PyErr_SetString(PyExc_ValueError,"packed code outside palette"); return NULL; }
            value=((const uint8_t *)PyBytes_AS_STRING(hot->palette))[value];
        }
    }
    return PyLong_FromLong(value);
}
static PyObject *span_hot_read(CompressedSpanHot *hot,PyObject *args,PyObject *kwargs) {
    PyObject *start=Py_None,*stop=Py_None;
    static char *names[]={"start","stop",NULL};
    if(!PyArg_ParseTupleAndKeywords(args,kwargs,"|OO:read",names,&start,&stop)) return NULL;
    PyObject *slice=PySlice_New(start,stop,Py_None);
    if(!slice) return NULL;
    Py_ssize_t first,last,step,length;
    int ok=PySlice_GetIndicesEx(slice,hot->length,&first,&last,&step,&length);
    Py_DECREF(slice);
    if(ok<0) return NULL;
    PyObject *out=PyBytes_FromStringAndSize(NULL,length);
    if(!out || !length) return out;
    uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
    memset(dst,hot->value,(size_t)length);
    Py_ssize_t begin=first>hot->start?first:hot->start;
    Py_ssize_t end=hot->start+hot->data->length;
    if(end>last) end=last;
    if(begin<end) {
        Array view=*hot->data;
        view.start+=(size_t)(begin-hot->start); view.length=end-begin;
        uint8_t *target=dst+(begin-first);
        unpackers[view.bits-1](&view,target);
        Py_ssize_t count=PyBytes_GET_SIZE(hot->palette);
        if(count) {
            const uint8_t *palette=(const uint8_t *)PyBytes_AS_STRING(hot->palette);
            for(Py_ssize_t i=0;i<view.length;i++) {
                if(target[i]>=count) { Py_DECREF(out); PyErr_SetString(PyExc_ValueError,"packed code outside palette"); return NULL; }
                target[i]=palette[target[i]];
            }
        }
    }
    return out;
}
/* Two passes: no packed value changes until every source value is known to
 * fit. The caller must retain this entry in its write-back cache. */
static PyObject *span_hot_try_write(CompressedSpanHot *hot,PyObject *args) {
    PyObject *position,*values;
    if(!PyArg_ParseTuple(args,"OO:try_write",&position,&values)) return NULL;
    if(!PyBytes_CheckExact(values)) { PyErr_SetString(PyExc_TypeError,"values must be exact bytes"); return NULL; }
    Py_ssize_t offset=PyNumber_AsSsize_t(position,PyExc_IndexError);
    if(offset==-1 && PyErr_Occurred()) return NULL;
    Py_ssize_t count=PyBytes_GET_SIZE(values);
    if(offset<0 || offset>hot->length || count>hot->length-offset) {
        PyErr_SetString(PyExc_IndexError,"write exceeds logical bounds"); return NULL;
    }
    if(!count) Py_RETURN_TRUE;
    if(offset<hot->start) Py_RETURN_FALSE;
    Py_ssize_t relative=offset-hot->start;
    if(relative>hot->data->length || count>hot->data->length-relative) Py_RETURN_FALSE;
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(values);
    Py_ssize_t palette_size=PyBytes_GET_SIZE(hot->palette);
    unsigned bound=1u<<hot->data->bits;
    uint16_t inverse[256];
    if(palette_size) {
        for(unsigned i=0;i<256;i++) inverse[i]=256;
        const uint8_t *palette=(const uint8_t *)PyBytes_AS_STRING(hot->palette);
        for(unsigned i=0;i<(unsigned)palette_size && i<bound;i++)
            if(inverse[palette[i]]==256) inverse[palette[i]]=(uint16_t)i;
        for(Py_ssize_t i=0;i<count;i++) if(inverse[src[i]]==256) Py_RETURN_FALSE;
        for(Py_ssize_t i=0;i<count;i++) put(hot->data,(size_t)(relative+i),(uint8_t)inverse[src[i]]);
    } else {
        for(Py_ssize_t i=0;i<count;i++) if(src[i]>=bound) Py_RETURN_FALSE;
        for(Py_ssize_t i=0;i<count;i++) put(hot->data,(size_t)(relative+i),src[i]);
    }
    hot->dirty=1;
    Py_RETURN_TRUE;
}
static PyGetSetDef span_hot_getters[]={
    {"data",(getter)span_hot_data,NULL,NULL,NULL},{"palette",(getter)span_hot_palette,NULL,NULL,NULL},
    {"default",(getter)span_hot_default,NULL,NULL,NULL},{"start",(getter)span_hot_start,NULL,NULL,NULL},
    {"length",(getter)span_hot_length,NULL,NULL,NULL},{"repeated",(getter)span_hot_repeated,NULL,NULL,NULL},
    {"dirty",(getter)span_hot_dirty,(setter)span_hot_set_dirty,NULL,NULL},{"nbytes",(getter)span_hot_nbytes,NULL,NULL,NULL},
    {NULL,NULL,NULL,NULL,NULL}
};
static PyMethodDef span_hot_methods[]={
    {"try_write",(PyCFunction)span_hot_try_write,METH_VARARGS,NULL},
    {"read",(PyCFunction)(void (*)(void))span_hot_read,METH_VARARGS|METH_KEYWORDS,NULL},
    {NULL,NULL,0,NULL}
};
static PyMappingMethods span_hot_mapping={.mp_subscript=(binaryfunc)span_hot_item};
static PyTypeObject CompressedSpanHotType={
    PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="tightarray._core._SpanHot",.tp_basicsize=sizeof(CompressedSpanHot),
    .tp_flags=Py_TPFLAGS_DEFAULT,.tp_new=span_hot_new,.tp_dealloc=(destructor)span_hot_dealloc,
    .tp_getset=span_hot_getters,.tp_methods=span_hot_methods,.tp_as_mapping=&span_hot_mapping
};
