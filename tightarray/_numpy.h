/* Python dispatch stays off the scalar indexing and native-kernel hot paths. */
static PyObject *numpy_call(const char *name,PyObject *args,PyObject *kwargs) {
    PyObject *module=PyImport_ImportModule("tightarray._numpy");
    if(!module) return NULL;
    PyObject *fn=PyObject_GetAttrString(module,name); Py_DECREF(module);
    if(!fn) return NULL;
    PyObject *out=PyObject_Call(fn,args,kwargs); Py_DECREF(fn); return out;
}
static PyObject *numpy_forward(PyObject *self,PyObject *args,PyObject *kwargs,const char *name) {
    Py_ssize_t n=PyTuple_GET_SIZE(args);
    PyObject *full=PyTuple_New(n+1); if(!full) return NULL;
    Py_INCREF(self); PyTuple_SET_ITEM(full,0,self);
    for(Py_ssize_t i=0;i<n;i++) { PyObject *v=PyTuple_GET_ITEM(args,i); Py_INCREF(v); PyTuple_SET_ITEM(full,i+1,v); }
    PyObject *out=numpy_call(name,full,kwargs); Py_DECREF(full); return out;
}
#define NUMPY_FORWARD(CNAME,PYNAME) \
static PyObject *CNAME(PyObject *self,PyObject *args,PyObject *kwargs) { return numpy_forward(self,args,kwargs,PYNAME); }
NUMPY_FORWARD(array_numpy,"asarray")
NUMPY_FORWARD(array_ufunc,"ufunc")
NUMPY_FORWARD(array_function,"array_function")
static PyObject *numpy_compare(PyObject *a,PyObject *b,int op) {
    PyObject *args=Py_BuildValue("OOi",a,b,op); if(!args) return NULL;
    PyObject *out=numpy_call("compare",args,NULL); Py_DECREF(args); return out;
}
#define NUMPY_BINARY(NAME) \
static PyObject *numpy_##NAME(PyObject *a,PyObject *b) { \
    PyObject *args=Py_BuildValue("OOs",a,b,#NAME); if(!args) return NULL; \
    PyObject *out=numpy_call("binary",args,NULL); Py_DECREF(args); return out; \
}
NUMPY_BINARY(add) NUMPY_BINARY(subtract) NUMPY_BINARY(multiply)
NUMPY_BINARY(true_divide) NUMPY_BINARY(floor_divide) NUMPY_BINARY(remainder)
NUMPY_BINARY(bitwise_and) NUMPY_BINARY(bitwise_or) NUMPY_BINARY(bitwise_xor)
NUMPY_BINARY(left_shift) NUMPY_BINARY(right_shift)
#define NUMPY_UNARY(NAME) \
static PyObject *numpy_##NAME(PyObject *a) { \
    PyObject *args=Py_BuildValue("Os",a,#NAME); if(!args) return NULL; \
    PyObject *out=numpy_call("unary",args,NULL); Py_DECREF(args); return out; \
}
NUMPY_UNARY(invert) NUMPY_UNARY(negative) NUMPY_UNARY(positive) NUMPY_UNARY(absolute)
static int array_bool(Array *a) {
    if(a->length!=1) { PyErr_SetString(PyExc_ValueError,"truth value requires exactly one element; use any/all or equals"); return -1; }
    return a->read(a,0)!=0;
}
static PyNumberMethods array_number={
    .nb_add=numpy_add,.nb_subtract=numpy_subtract,.nb_multiply=numpy_multiply,
    .nb_true_divide=numpy_true_divide,.nb_floor_divide=numpy_floor_divide,.nb_remainder=numpy_remainder,
    .nb_and=numpy_bitwise_and,.nb_or=numpy_bitwise_or,.nb_xor=numpy_bitwise_xor,
    .nb_lshift=numpy_left_shift,.nb_rshift=numpy_right_shift,
    .nb_invert=numpy_invert,.nb_negative=numpy_negative,.nb_positive=numpy_positive,.nb_absolute=numpy_absolute,
    .nb_bool=(inquiry)array_bool
};
static PyObject *array_equals(Array *a,PyObject *other) {
    if(!PyObject_TypeCheck(other,&ArrayType)) Py_RETURN_FALSE;
    return array_compare((PyObject *)a,other,Py_EQ);
}
static PyObject *array_shape(Array *a,void *c) { return Py_BuildValue("(n)",a->length); }
static PyObject *array_ndim(Array *a,void *c) { return PyLong_FromLong(1); }
static PyObject *array_size(Array *a,void *c) { return PyLong_FromSsize_t(a->length); }

static PyObject *array_dtype(Array *a,void *c) {
    PyObject *args=PyTuple_New(0); if(!args) return NULL;
    PyObject *out=numpy_call("dtype",args,NULL); Py_DECREF(args); return out;
}
