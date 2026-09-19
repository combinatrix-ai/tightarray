/* Private physical buffer exporter. Do not give Array a buffer protocol: NumPy
 * must continue to see its logical values through __array__, not packed words.
 * Array storage has fixed size/width and no reinitialization/resizing path.
 * Holding the Array (or slice) pins its root allocation for the buffer lifetime. */
typedef struct { PyObject_HEAD Array *array; } WordBuffer;
static int wordbuffer_getbuffer(WordBuffer *self,Py_buffer *buf,int flags) {
    Array *a=self->array;
    Array *root=a->owner?(Array *)a->owner:a;
    if(root->words>(size_t)PY_SSIZE_T_MAX/8) { PyErr_NoMemory(); return -1; }
    return PyBuffer_FillInfo(buf,(PyObject *)self,root->data,(Py_ssize_t)root->words*8,0,flags);
}
static void wordbuffer_dealloc(WordBuffer *self) { Py_DECREF(self->array); PyObject_Del(self); }
static PyBufferProcs wordbuffer_protocol={.bf_getbuffer=(getbufferproc)wordbuffer_getbuffer};
static PyTypeObject WordBufferType={
    PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="tightarray._WordBuffer",.tp_basicsize=sizeof(WordBuffer),
    .tp_flags=Py_TPFLAGS_DEFAULT,.tp_dealloc=(destructor)wordbuffer_dealloc,
    .tp_as_buffer=&wordbuffer_protocol
};
static PyObject *array_word_view(Array *a,PyObject *unused) {
    WordBuffer *holder=PyObject_New(WordBuffer,&WordBufferType);
    if(!holder)return NULL;
    holder->array=a; Py_INCREF(a);
    PyObject *buffer=PyMemoryView_FromObject((PyObject *)holder);
    Py_DECREF(holder);
    if(!buffer)return NULL;
    return Py_BuildValue("Nn",buffer,(Py_ssize_t)a->start);
}
