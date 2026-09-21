/* Native packed cache entry. Exact owned references cannot form cycles. */
typedef struct {
    PyObject_HEAD
    Array *data;
    PyObject *palette;
    int dirty;
    Py_ssize_t length;
} CompressedHot;

static PyObject *compressed_hot_new(PyTypeObject *type,PyObject *args,PyObject *kwargs) {
    PyObject *data,*palette=NULL,*dirty=Py_False,*logical=NULL;
    static char *names[]={"data","palette","dirty","length",NULL};
    if(!PyArg_ParseTupleAndKeywords(args,kwargs,"O|OO$O:_Hot",names,&data,&palette,&dirty,&logical)) return NULL;
    if(!Py_IS_TYPE(data,&ArrayType)) {
        PyErr_SetString(PyExc_TypeError,"data must be an exact Array"); return NULL;
    }
    if(palette && (!PyBytes_CheckExact(palette) || PyBytes_GET_SIZE(palette)>256)) {
        PyErr_SetString(PyExc_TypeError,"palette must be exact bytes of length at most 256"); return NULL;
    }
    if(!PyBool_Check(dirty)) {
        PyErr_SetString(PyExc_TypeError,"dirty must be bool"); return NULL;
    }
    Py_ssize_t length=((Array *)data)->length;
    if(logical) {
        length=PyNumber_AsSsize_t(logical,PyExc_OverflowError);
        if(length==-1 && PyErr_Occurred()) return NULL;
        if(length<((Array *)data)->length || (!((Array *)data)->length && length)) {
            PyErr_SetString(PyExc_ValueError,"logical length must cover a nonempty pattern"); return NULL;
        }
    }
    CompressedHot *hot=PyObject_New(CompressedHot,type);
    if(!hot) return NULL;
    hot->data=(Array *)data; Py_INCREF(data);
    if(palette) { hot->palette=palette; Py_INCREF(palette); }
    else hot->palette=PyBytes_FromStringAndSize("",0);
    if(!hot->palette) { Py_DECREF(data); PyObject_Del(hot); return NULL; }
    hot->dirty=dirty==Py_True; hot->length=length;
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
static PyObject *compressed_hot_repeated(CompressedHot *hot,void *unused) {
    return PyBool_FromLong(hot->length!=hot->data->length);
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
    if(index<0) index+=hot->length;
    if(index<0 || index>=hot->length) { PyErr_SetString(PyExc_IndexError,"cache index out of range"); return NULL; }
    if(hot->length!=hot->data->length) index%=hot->data->length;
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
    int ok=PySlice_GetIndicesEx(slice,hot->length,&first,&last,&step,&length);
    Py_DECREF(slice);
    if(ok<0) return NULL;
    PyObject *out;
    Py_ssize_t decoded=length;
    if(hot->length==hot->data->length) {
        Array view=*hot->data;
        view.start+=(size_t)first; view.length=length;
        out=array_bytes(&view,NULL);
    } else {
        out=PyBytes_FromStringAndSize(NULL,length);
        if(!out) return NULL;
        Py_ssize_t pattern=hot->data->length, offset=first%pattern;
        if(decoded>pattern) decoded=pattern;
        Py_ssize_t initial=pattern-offset;
        if(initial>decoded) initial=decoded;
        uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
        Array view=*hot->data;
        view.start+=(size_t)offset; view.length=initial;
        unpackers[view.bits-1](&view,dst);
        if(decoded>initial) {
            view=*hot->data; view.length=decoded-initial;
            unpackers[view.bits-1](&view,dst+initial);
        }
    }
    if(!out) return NULL;
    Py_ssize_t palette_size=PyBytes_GET_SIZE(hot->palette);
    if(palette_size) {
        const uint8_t *palette=(const uint8_t *)PyBytes_AS_STRING(hot->palette);
        uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
        for(Py_ssize_t i=0;i<decoded;i++) {
            if(dst[i]>=palette_size) {
                Py_DECREF(out); PyErr_SetString(PyExc_ValueError,"packed code outside palette"); return NULL;
            }
            dst[i]=palette[dst[i]];
        }
    }
    uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
    while(decoded<length) {
        Py_ssize_t count=length-decoded;
        if(count>decoded) count=decoded;
        memcpy(dst+decoded,dst,(size_t)count); decoded+=count;
    }
    return out;
}
/* Caller validates the physical range; preflight all values before mutation. */
static int compressed_hot_write_values(Array *data,PyObject *palette_object,
                                       Py_ssize_t relative,PyObject *values) {
    Py_ssize_t count=PyBytes_GET_SIZE(values);
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(values);
    Py_ssize_t palette_size=PyBytes_GET_SIZE(palette_object);
    if(!palette_size && data->bits==8) {
        /* Both layouts are contiguous bytes at width 8, including views. */
        memcpy((uint8_t *)data->data+data->start+(size_t)relative,src,(size_t)count);
        return 1;
    }
    unsigned bound=1u<<data->bits;
    uint16_t inverse[256];
    if(palette_size) {
        for(unsigned i=0;i<256;i++) inverse[i]=256;
        const uint8_t *palette=(const uint8_t *)PyBytes_AS_STRING(palette_object);
        for(unsigned i=0;i<(unsigned)palette_size && i<bound;i++)
            if(inverse[palette[i]]==256) inverse[palette[i]]=(uint16_t)i;
        for(Py_ssize_t i=0;i<count;i++) if(inverse[src[i]]==256) return 0;
        for(Py_ssize_t i=0;i<count;i++) put(data,(size_t)(relative+i),(uint8_t)inverse[src[i]]);
    } else {
        for(Py_ssize_t i=0;i<count;i++) if(src[i]>=bound) return 0;
        for(Py_ssize_t i=0;i<count;i++) put(data,(size_t)(relative+i),src[i]);
    }
    return 1;
}
static PyObject *compressed_hot_try_write(CompressedHot *hot,PyObject *args) {
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
    if(hot->length!=hot->data->length) Py_RETURN_FALSE;
    if(!compressed_hot_write_values(hot->data,hot->palette,offset,values)) Py_RETURN_FALSE;
    hot->dirty=1;
    Py_RETURN_TRUE;
}
static PyGetSetDef compressed_hot_getters[]={
    {"data",(getter)compressed_hot_data,NULL,NULL,NULL},
    {"palette",(getter)compressed_hot_palette,NULL,NULL,NULL},
    {"repeated",(getter)compressed_hot_repeated,NULL,NULL,NULL},
    {"dirty",(getter)compressed_hot_dirty,(setter)compressed_hot_set_dirty,NULL,NULL},
    {"nbytes",(getter)compressed_hot_nbytes,NULL,NULL,NULL},
    {NULL,NULL,NULL,NULL,NULL}
};
static PyMethodDef compressed_hot_methods[]={
    {"try_write",(PyCFunction)compressed_hot_try_write,METH_VARARGS,NULL},
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
