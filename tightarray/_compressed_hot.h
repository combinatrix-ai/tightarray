/* Native packed cache entry. Exact owned references cannot form cycles. */
typedef struct {
    PyObject_HEAD
    Array *data;
    PyObject *palette;
    int dirty;
} CompressedHot;

static PyObject *compressed_hot_new(PyTypeObject *type,PyObject *args,PyObject *kwargs) {
    PyObject *data,*palette=NULL,*dirty=Py_False;
    static char *names[]={"data","palette","dirty",NULL};
    if(!PyArg_ParseTupleAndKeywords(args,kwargs,"O|OO:_Hot",names,&data,&palette,&dirty)) return NULL;
    if(!Py_IS_TYPE(data,&ArrayType)) {
        PyErr_SetString(PyExc_TypeError,"data must be an exact Array"); return NULL;
    }
    if(palette && (!PyBytes_CheckExact(palette) || PyBytes_GET_SIZE(palette)>256)) {
        PyErr_SetString(PyExc_TypeError,"palette must be exact bytes of length at most 256"); return NULL;
    }
    if(!PyBool_Check(dirty)) {
        PyErr_SetString(PyExc_TypeError,"dirty must be bool"); return NULL;
    }
    CompressedHot *hot=PyObject_New(CompressedHot,type);
    if(!hot) return NULL;
    hot->data=(Array *)data; Py_INCREF(data);
    if(palette) { hot->palette=palette; Py_INCREF(palette); }
    else hot->palette=PyBytes_FromStringAndSize("",0);
    if(!hot->palette) { Py_DECREF(data); PyObject_Del(hot); return NULL; }
    hot->dirty=dirty==Py_True;
    return (PyObject *)hot;
}
static void compressed_hot_dealloc(CompressedHot *hot) {
    Py_DECREF(hot->data); Py_DECREF(hot->palette); PyObject_Del(hot);
}
static PyObject *compressed_hot_data(CompressedHot *hot,void *unused) {
    Py_INCREF(hot->data); return (PyObject *)hot->data;
}
static PyObject *compressed_hot_palette(CompressedHot *hot,void *unused) {
    Py_INCREF(hot->palette); return hot->palette;
}
static PyObject *compressed_hot_dirty(CompressedHot *hot,void *unused) {
    return PyBool_FromLong(hot->dirty);
}
static int compressed_hot_set_dirty(CompressedHot *hot,PyObject *value,void *unused) {
    if(!value || !PyBool_Check(value)) {
        PyErr_SetString(PyExc_TypeError,"dirty must be bool"); return -1;
    }
    hot->dirty=value==Py_True; return 0;
}
static PyObject *compressed_hot_nbytes(CompressedHot *hot,void *unused) {
    Array *data=hot->data;
    size_t bytes=data->owner?0:(data->words?data->words:1)*8;
    return PyLong_FromSize_t(bytes+(size_t)PyBytes_GET_SIZE(hot->palette));
}
static PyObject *compressed_hot_item(CompressedHot *hot,PyObject *key) {
    if(!PyIndex_Check(key)) { PyErr_SetString(PyExc_TypeError,"index must be an integer"); return NULL; }
    Py_ssize_t index=PyNumber_AsSsize_t(key,PyExc_IndexError);
    if(index==-1 && PyErr_Occurred()) return NULL;
    if(normalize(hot->data,&index)<0) return NULL;
    uint8_t value=hot->data->read(hot->data,(size_t)index);
    Py_ssize_t palette_size=PyBytes_GET_SIZE(hot->palette);
    if(palette_size) {
        if(value>=palette_size) { PyErr_SetString(PyExc_ValueError,"packed code outside palette"); return NULL; }
        value=((const uint8_t *)PyBytes_AS_STRING(hot->palette))[value];
    }
    return PyLong_FromLong(value);
}
static PyObject *compressed_hot_read(CompressedHot *hot,PyObject *args,PyObject *kwargs) {
    PyObject *start=Py_None,*stop=Py_None;
    static char *names[]={"start","stop",NULL};
    if(!PyArg_ParseTupleAndKeywords(args,kwargs,"|OO:read",names,&start,&stop)) return NULL;
    PyObject *slice=PySlice_New(start,stop,Py_None);
    if(!slice) return NULL;
    Py_ssize_t first,last,step,length;
    int ok=PySlice_GetIndicesEx(slice,hot->data->length,&first,&last,&step,&length);
    Py_DECREF(slice);
    if(ok<0) return NULL;
    Array view=*hot->data;
    view.start+=(size_t)first; view.length=length;
    PyObject *out=array_bytes(&view,NULL);
    if(!out) return NULL;
    Py_ssize_t palette_size=PyBytes_GET_SIZE(hot->palette);
    if(palette_size) {
        const uint8_t *palette=(const uint8_t *)PyBytes_AS_STRING(hot->palette);
        uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
        for(Py_ssize_t i=0;i<length;i++) {
            if(dst[i]>=palette_size) {
                Py_DECREF(out); PyErr_SetString(PyExc_ValueError,"packed code outside palette"); return NULL;
            }
            dst[i]=palette[dst[i]];
        }
    }
    return out;
}
static PyGetSetDef compressed_hot_getters[]={
    {"data",(getter)compressed_hot_data,NULL,NULL,NULL},
    {"palette",(getter)compressed_hot_palette,NULL,NULL,NULL},
    {"dirty",(getter)compressed_hot_dirty,(setter)compressed_hot_set_dirty,NULL,NULL},
    {"nbytes",(getter)compressed_hot_nbytes,NULL,NULL,NULL},
    {NULL,NULL,NULL,NULL,NULL}
};
static PyMethodDef compressed_hot_methods[]={
    {"read",(PyCFunction)(void (*)(void))compressed_hot_read,METH_VARARGS|METH_KEYWORDS,NULL},
    {NULL,NULL,0,NULL}
};
static PyMappingMethods compressed_hot_mapping={.mp_subscript=(binaryfunc)compressed_hot_item};
static PyTypeObject CompressedHotType={
    PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="tightarray._core._Hot",.tp_basicsize=sizeof(CompressedHot),
    .tp_flags=Py_TPFLAGS_DEFAULT,.tp_new=compressed_hot_new,
    .tp_dealloc=(destructor)compressed_hot_dealloc,
    .tp_getset=compressed_hot_getters,.tp_methods=compressed_hot_methods,
    .tp_as_mapping=&compressed_hot_mapping
};
