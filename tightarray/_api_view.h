/* C-backed Array API metadata and direct scalar slots. Python supplies fallbacks. */
typedef struct {
    PyObject_HEAD
    PyObject *storage,*shape,*strides,*dtype,*numpy;
    Py_ssize_t offset;
    int boolean;
} APIView;
static PyTypeObject APIViewType;
static int api_traverse(APIView *v,visitproc visit,void *arg) {
    Py_VISIT(v->storage); Py_VISIT(v->shape); Py_VISIT(v->strides); Py_VISIT(v->dtype); Py_VISIT(v->numpy); return 0;
}
static int api_clear(APIView *v) { Py_CLEAR(v->storage); Py_CLEAR(v->shape); Py_CLEAR(v->strides); Py_CLEAR(v->dtype); Py_CLEAR(v->numpy); return 0; }
static void api_dealloc(APIView *v) { PyObject_GC_UnTrack(v); api_clear(v); Py_TYPE(v)->tp_free((PyObject *)v); }
static Array *api_data(APIView *v) {
    if(!v->storage || !PyObject_TypeCheck(v->storage,&APIStorageType)) return NULL;
    return ((APIStorage *)v->storage)->data;
}
static int api_scalar_position(APIView *v,PyObject *key,Py_ssize_t *pos) {
    Array *a=api_data(v);
    if(!a || !v->shape || !PyTuple_Check(v->shape) || !v->strides || !PyTuple_Check(v->strides)) return 0;
    Py_ssize_t ndim=PyTuple_GET_SIZE(v->shape);
    __int128 offset=v->offset;
    if(ndim==1 && PyLong_CheckExact(key) && PyTuple_GET_SIZE(v->strides)==1) {
        Py_ssize_t n=PyLong_AsSsize_t(PyTuple_GET_ITEM(v->shape,0)); if(PyErr_Occurred()) return -1;
        Py_ssize_t stride=PyLong_AsSsize_t(PyTuple_GET_ITEM(v->strides,0)); if(PyErr_Occurred()) return -1;
        Py_ssize_t i=PyNumber_AsSsize_t(key,PyExc_IndexError); if(PyErr_Occurred()) return -1;
        if(n<0) { PyErr_SetString(PyExc_ValueError,"negative dimension"); return -1; }
        if(i<0) i+=n;
        if(i<0 || i>=n) { PyErr_SetString(PyExc_IndexError,"index out of bounds"); return -1; }
        offset+=(__int128)i*stride;
    } else if(ndim>0 && PyTuple_Check(key) && PyTuple_GET_SIZE(key)==ndim && PyTuple_GET_SIZE(v->strides)==ndim) {
        for(Py_ssize_t d=0;d<ndim;d++) if(!PyLong_CheckExact(PyTuple_GET_ITEM(key,d))) return 0;
        for(Py_ssize_t d=0;d<ndim;d++) {
            PyObject *item=PyTuple_GET_ITEM(key,d);
            Py_ssize_t n=PyLong_AsSsize_t(PyTuple_GET_ITEM(v->shape,d)); if(PyErr_Occurred()) return -1;
            Py_ssize_t stride=PyLong_AsSsize_t(PyTuple_GET_ITEM(v->strides,d)); if(PyErr_Occurred()) return -1;
            Py_ssize_t i=PyNumber_AsSsize_t(item,PyExc_IndexError); if(PyErr_Occurred()) return -1;
            if(n<0) { PyErr_SetString(PyExc_ValueError,"negative dimension"); return -1; }
            if(i<0) i+=n;
            if(i<0 || i>=n) { PyErr_SetString(PyExc_IndexError,"index out of bounds"); return -1; }
            offset+=(__int128)i*stride;
            if(offset<0 || offset>=a->length) { PyErr_SetString(PyExc_IndexError,"view exceeds storage"); return -1; }
        }
    } else if(!(ndim==0 && (key==Py_Ellipsis || (PyTuple_Check(key) && PyTuple_GET_SIZE(key)==0)))) return 0;
    if(offset<0 || offset>=a->length) { PyErr_SetString(PyExc_IndexError,"view exceeds storage"); return -1; }
    *pos=(Py_ssize_t)offset; return 1;
}
static APIView *api_make_view(APIView *v,PyObject *shape,PyObject *strides,Py_ssize_t offset) {
    APIView *out=(APIView *)Py_TYPE(v)->tp_alloc(Py_TYPE(v),0); if(!out) return NULL;
    out->storage=Py_NewRef(v->storage); out->dtype=Py_NewRef(v->dtype); out->numpy=Py_NewRef(Py_None);
    out->shape=Py_NewRef(shape); out->strides=Py_NewRef(strides); out->offset=offset; out->boolean=v->boolean;
    return out;
}
static PyObject *api_new_view(APIView *v,PyObject *args) {
    PyObject *shape,*strides; Py_ssize_t offset; ArrayView descriptor;
    if(!PyArg_ParseTuple(args,"O!O!n",&PyTuple_Type,&shape,&PyTuple_Type,&strides,&offset)) return NULL;
    Array *a=api_data(v);
    if(!a || !v->dtype) { PyErr_SetString(PyExc_RuntimeError,"packed view requires initialized storage and dtype"); return NULL; }
    if(parse_view(a,shape,strides,offset,&descriptor)<0) return NULL;
    return (PyObject *)api_make_view(v,shape,strides,offset);
}
static PyObject *api_subscript(APIView *v,PyObject *key) {
    Py_ssize_t pos; int found=api_scalar_position(v,key,&pos); if(found<0) return NULL;
    if(found && v->dtype) {
        PyObject *empty=PyTuple_New(0); if(!empty) return NULL;
        APIView *out=api_make_view(v,empty,empty,pos); Py_DECREF(empty); return (PyObject *)out;
    }
    return PyObject_CallMethod((PyObject *)v,"_getitem","(O)",key);
}
static int api_assign(APIView *v,PyObject *key,PyObject *value) {
    if(!value) { PyErr_SetString(PyExc_TypeError,"array elements cannot be deleted"); return -1; }
    if(PyLong_CheckExact(value)) {
        Py_ssize_t pos; int found=api_scalar_position(v,key,&pos); if(found<0) return -1;
        if(found) {
            long n;
            if(v->boolean) { n=PyObject_IsTrue(value); if(n<0) return -1; }
            else {
                int overflow=0; n=PyLong_AsLongAndOverflow(value,&overflow);
                if(PyErr_Occurred()) return -1;
                if(overflow || n<0 || n>255) { PyErr_SetString(PyExc_OverflowError,"integer out of bounds for uint8"); return -1; }
            }
            unsigned bits=1; while((unsigned)n>>bits) bits++;
            APIStorage *s=(APIStorage *)v->storage;
            if(storage_widen(s,bits)<0) return -1;
            put(s->data,pos,(uint8_t)n); return 0;
        }
    }
    PyObject *r=PyObject_CallMethod((PyObject *)v,"_setitem","OO",key,value); if(!r) return -1;
    Py_DECREF(r); return 0;
}
static int api_scalar_ready(APIView *v) {
    if(!v->shape || !PyTuple_Check(v->shape) || PyTuple_GET_SIZE(v->shape)) { PyErr_SetString(PyExc_TypeError,"scalar conversion requires a zero-dimensional array"); return -1; }
    Array *a=api_data(v);
    if(a && (v->offset<0 || v->offset>=a->length)) { PyErr_SetString(PyExc_IndexError,"view exceeds storage"); return -1; }
    if(!a && (!v->numpy || v->numpy==Py_None)) { PyErr_SetString(PyExc_RuntimeError,"uninitialized array"); return -1; }
    return 0;
}
static PyObject *api_int(APIView *v) {
    if(api_scalar_ready(v)<0) return NULL;
    Array *a=api_data(v); return a?PyLong_FromLong(a->read(a,v->offset)):PyNumber_Long(v->numpy);
}
static PyObject *api_float(APIView *v) {
    if(api_scalar_ready(v)<0) return NULL;
    Array *a=api_data(v); return a?PyFloat_FromDouble(a->read(a,v->offset)):PyNumber_Float(v->numpy);
}
static PyObject *api_dtype(APIView *v,void *unused) { if(!v->dtype) { PyErr_SetString(PyExc_AttributeError,"uninitialized dtype"); return NULL; } return Py_NewRef(v->dtype); }
static int api_set_dtype(APIView *v,PyObject *value,void *unused) {
    if(!value) { PyErr_SetString(PyExc_TypeError,"cannot delete dtype"); return -1; }
    PyObject *kind=PyObject_GetAttrString(value,"kind"); if(!kind) return -1;
    int boolean=PyUnicode_Check(kind) && PyUnicode_CompareWithASCIIString(kind,"b")==0; Py_DECREF(kind);
    if(PyErr_Occurred()) return -1;
    Py_INCREF(value); Py_XSETREF(v->dtype,value); v->boolean=boolean; return 0;
}
static PyMemberDef api_members[]={
    {"_storage",T_OBJECT_EX,offsetof(APIView,storage),0,NULL},{"_shape",T_OBJECT_EX,offsetof(APIView,shape),0,NULL},
    {"_strides",T_OBJECT_EX,offsetof(APIView,strides),0,NULL},{"_offset",T_PYSSIZET,offsetof(APIView,offset),0,NULL},
    {"_numpy",T_OBJECT_EX,offsetof(APIView,numpy),0,NULL},{0}};
static PyGetSetDef api_getset[]={{"_dtype",(getter)api_dtype,(setter)api_set_dtype,NULL,NULL},{0}};
static PyMethodDef api_methods[]={{"_new_view",(PyCFunction)api_new_view,METH_VARARGS,NULL},{0}};
static PyObject *api_item(APIView *v,Py_ssize_t i) {
    PyObject *key=PyLong_FromSsize_t(i); if(!key) return NULL;
    PyObject *out=api_subscript(v,key); Py_DECREF(key); return out;
}
static PySequenceMethods api_sequence={.sq_item=(ssizeargfunc)api_item};
static PyMappingMethods api_mapping={.mp_subscript=(binaryfunc)api_subscript,.mp_ass_subscript=(objobjargproc)api_assign};
static PyNumberMethods api_number={.nb_int=(unaryfunc)api_int,.nb_float=(unaryfunc)api_float};
static PyTypeObject APIViewType={PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="tightarray._core._APIView",.tp_basicsize=sizeof(APIView),.tp_flags=Py_TPFLAGS_DEFAULT|Py_TPFLAGS_BASETYPE|Py_TPFLAGS_HAVE_GC,
    .tp_new=PyType_GenericNew,.tp_dealloc=(destructor)api_dealloc,.tp_traverse=(traverseproc)api_traverse,.tp_clear=(inquiry)api_clear,
    .tp_members=api_members,.tp_getset=api_getset,.tp_methods=api_methods,.tp_as_mapping=&api_mapping,.tp_as_sequence=&api_sequence,.tp_as_number=&api_number};
