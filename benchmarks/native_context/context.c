#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <blosc2.h>
#include <string.h>

typedef struct {
    PyObject_HEAD
    blosc2_context *context;
    Py_ssize_t length;
} Context;

static PyObject *context_new(PyTypeObject *type,PyObject *args,PyObject *kwargs) {
    const char *codec; PyObject *length_object,*shuffle;
    static char *names[]={"codec","length","shuffle",NULL};
    if(!PyArg_ParseTupleAndKeywords(args,kwargs,"sOO:CompressionContext",names,&codec,&length_object,&shuffle)) return NULL;
    if(!PyBool_Check(shuffle)) { PyErr_SetString(PyExc_TypeError,"shuffle must be bool"); return NULL; }
    Py_ssize_t length=PyNumber_AsSsize_t(length_object,PyExc_OverflowError);
    if(length==-1 && PyErr_Occurred()) return NULL;
    if(length<0 || length>BLOSC2_MAX_BUFFERSIZE) { PyErr_SetString(PyExc_ValueError,"invalid payload length"); return NULL; }
    blosc2_cparams params=BLOSC2_CPARAMS_DEFAULTS;
    if(!strcmp(codec,"lz4")) params.compcode=BLOSC_LZ4;
    else if(!strcmp(codec,"zstd")) params.compcode=BLOSC_ZSTD;
    else { PyErr_SetString(PyExc_ValueError,"codec must be lz4 or zstd"); return NULL; }
    params.clevel=5; params.typesize=1; params.nthreads=1;
    params.splitmode=BLOSC_AUTO_SPLIT;
    memset(params.filters,0,sizeof(params.filters));
    params.filters[0]=shuffle==Py_True?BLOSC_BITSHUFFLE:BLOSC_NOFILTER;
    Context *self=(Context *)type->tp_alloc(type,0);
    if(!self) return NULL;
    self->length=length;
    self->context=blosc2_create_cctx(params);
    if(!self->context) { Py_DECREF(self); PyErr_SetString(PyExc_RuntimeError,"compression context allocation failed"); return NULL; }
    return (PyObject *)self;
}
static void context_dealloc(Context *self) {
    if(self->context) blosc2_free_ctx(self->context);
    Py_TYPE(self)->tp_free((PyObject *)self);
}
static PyObject *context_close(Context *self,PyObject *unused) {
    if(self->context) { blosc2_free_ctx(self->context); self->context=NULL; }
    Py_RETURN_NONE;
}
static PyObject *context_compress(Context *self,PyObject *raw) {
    if(!PyBytes_CheckExact(raw)) { PyErr_SetString(PyExc_TypeError,"raw must be exact bytes"); return NULL; }
    if(PyBytes_GET_SIZE(raw)!=self->length) { PyErr_SetString(PyExc_ValueError,"payload length differs from context"); return NULL; }
    if(!self->context) { PyErr_SetString(PyExc_RuntimeError,"context is closed"); return NULL; }
    Py_ssize_t capacity=self->length+BLOSC2_MAX_OVERHEAD;
    PyObject *output=PyBytes_FromStringAndSize(NULL,capacity);
    if(!output) return NULL;
    /* Keep the GIL: this context cannot be used concurrently or closed mid-call. */
    int size=blosc2_compress_ctx(self->context,PyBytes_AS_STRING(raw),(int32_t)self->length,
                                PyBytes_AS_STRING(output),(int32_t)capacity);
    if(size<=0 || size>capacity) {
        Py_DECREF(output); blosc2_free_ctx(self->context); self->context=NULL;
        PyErr_SetString(PyExc_RuntimeError,"compression failed; context retired"); return NULL;
    }
    if(size==capacity) return output;
    PyObject *result=PyBytes_FromStringAndSize(PyBytes_AS_STRING(output),size);
    Py_DECREF(output);
    return result;
}
static PyMethodDef context_methods[]={
    {"compress",(PyCFunction)context_compress,METH_O,NULL},
    {"close",(PyCFunction)context_close,METH_NOARGS,NULL},
    {NULL,NULL,0,NULL}
};
static PyTypeObject ContextType={
    PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="ta_ccontext.CompressionContext",.tp_basicsize=sizeof(Context),
    .tp_flags=Py_TPFLAGS_DEFAULT,.tp_new=context_new,.tp_dealloc=(destructor)context_dealloc,
    .tp_methods=context_methods
};
static PyModuleDef module={PyModuleDef_HEAD_INIT,.m_name="ta_ccontext",.m_size=-1};
PyMODINIT_FUNC PyInit_ta_ccontext(void) {
    /* This wheel embeds its own Blosc; our linked dylib is an independent
     * experimental image. Initialize once, and never destroy process globals. */
    static int initialized=0;
    if(!initialized) { blosc2_init(); initialized=1; }
    if(PyType_Ready(&ContextType)<0) return NULL;
    PyObject *result=PyModule_Create(&module);
    if(!result) return NULL;
    if(PyModule_AddObjectRef(result,"CompressionContext",(PyObject *)&ContextType)<0) { Py_DECREF(result); return NULL; }
    return result;
}
