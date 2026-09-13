/* Shared ownership cell. Widening never allocates an unpacked root buffer. */
#include <structmember.h>
typedef struct { PyObject_HEAD Array *data; } APIStorage;
static PyTypeObject APIStorageType;
static int storage_init(APIStorage *s,PyObject *args,PyObject *kw) {
    if(s->data) { PyErr_SetString(PyExc_RuntimeError,"storage cannot be reinitialized"); return -1; }
    Array *a; static char *names[]={"data",NULL};
    if(!PyArg_ParseTupleAndKeywords(args,kw,"O!",names,&ArrayType,&a)) return -1;
    Py_INCREF(a); Py_XSETREF(s->data,a); return 0;
}
static void storage_dealloc(APIStorage *s) { Py_XDECREF(s->data); Py_TYPE(s)->tp_free((PyObject *)s); }
static PyObject *storage_data(APIStorage *s,void *unused) { if(!s->data) { PyErr_SetString(PyExc_RuntimeError,"uninitialized storage"); return NULL; } return Py_NewRef(s->data); }
static int storage_set_data(APIStorage *s,PyObject *value,void *unused) {
    if(!value || !PyObject_TypeCheck(value,&ArrayType)) { PyErr_SetString(PyExc_TypeError,"storage requires a native array"); return -1; }
    if(s->data && ((Array *)value)->length!=s->data->length) { PyErr_SetString(PyExc_ValueError,"storage length cannot change"); return -1; }
    Py_INCREF(value); Py_XSETREF(s->data,(Array *)value); return 0;
}
static int storage_widen(APIStorage *s,unsigned bits) {
    if(!s->data) { PyErr_SetString(PyExc_RuntimeError,"uninitialized storage"); return -1; }
    if(bits<=s->data->bits) return 0;
    /* Cold path only: warn/reject before allocating or changing shared storage. */
    PyObject *policy=PyImport_ImportModule("tightarray.array_api._policy");
    if(!policy) return -1;
    PyObject *ok=PyObject_CallMethod(policy,"_check_widen","IIn",s->data->bits,bits,s->data->length);
    Py_DECREF(policy);
    if(!ok) return -1;
    Py_DECREF(ok);
    /* A custom warning handler may have widened this storage itself. */
    if(bits<=s->data->bits) return 0;
    Array *a=allocate(s->data->length,bits,s->data->aligned); if(!a) return -1;
    if(bits==8) unpack_range(s->data,0,a->length,(uint8_t *)a->data);
    else {
        uint8_t block[1024];
        unsigned lanes=64/bits;
        Py_ssize_t step=a->aligned?(1024/lanes)*lanes:1024;
        if(a->aligned) {
            unsigned input_lanes=64/s->data->bits, x=lanes,y=input_lanes;
            while(y) { unsigned r=x%y; x=y; y=r; }
            unsigned period=(lanes/x)*input_lanes;
            if(period<=1024) step=(1024/period)*period;
        }
        for(Py_ssize_t base=0;base<a->length;base+=step) {
            Py_ssize_t n=a->length-base<step?a->length-base:step;
            unpack_range(s->data,base,n,block);
            Array span=*a; span.start=0; span.length=n;
            span.data+=a->aligned?(size_t)base/lanes:(size_t)base*bits/64;
            span.words=a->aligned?((size_t)n+lanes-1)/lanes:((size_t)n*bits+63)/64;
#if defined(__aarch64__) && !defined(TIGHTARRAY_NO_NEON)
            simdpackers[bits-1](&span,block);
#else
            packers[bits-1](&span,block);
#endif
        }
    }
    Py_SETREF(s->data,a); return 0;
}
static PyObject *storage_widen_method(APIStorage *s,PyObject *arg) {
    long bits=PyLong_AsLong(arg); if(bits==-1 && PyErr_Occurred()) return NULL;
    if(bits<1 || bits>8) { PyErr_SetString(PyExc_ValueError,"width must be between 1 and 8"); return NULL; }
    if(storage_widen(s,(unsigned)bits)<0) return NULL; Py_RETURN_NONE;
}
static PyMethodDef storage_methods[]={{"widen",(PyCFunction)storage_widen_method,METH_O,NULL},{0}};
static PyGetSetDef storage_getset[]={{"data",(getter)storage_data,(setter)storage_set_data,NULL,NULL},{0}};
static PyTypeObject APIStorageType={PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="tightarray._core._Storage",.tp_basicsize=sizeof(APIStorage),.tp_flags=Py_TPFLAGS_DEFAULT,
    .tp_new=PyType_GenericNew,.tp_init=(initproc)storage_init,.tp_dealloc=(destructor)storage_dealloc,
    .tp_methods=storage_methods,.tp_getset=storage_getset};
