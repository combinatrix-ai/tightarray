#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "tightarray currently requires a little-endian target"
#endif

typedef struct Array Array;
typedef uint8_t (*Reader)(const Array *, size_t);
struct Array {
    PyObject_HEAD
    uint64_t *data;
    Py_ssize_t length;
    size_t start, words;
    unsigned bits, aligned;
    Reader read;
    PyObject *owner;
};
static PyTypeObject ArrayType;

/* Constant widths let clang remove divisions and specialize boundary cases. */
#define READERS(B) \
static uint8_t p##B(const Array *a, size_t i) { \
    size_t pos = (a->start+i)*(B), w=pos>>6; unsigned s=pos&63; \
    uint64_t v=a->data[w]>>s; \
    if (s+(B)>64) v |= a->data[w+1]<<(64-s); \
    return v & ((1u<<(B))-1); \
} \
static uint8_t a##B(const Array *a, size_t i) { \
    size_t pos=a->start+i; \
    return (a->data[pos/(64/(B))] >> ((pos%(64/(B)))*(B))) & ((1u<<(B))-1); \
}
READERS(1) READERS(2) READERS(3) READERS(4)
READERS(5) READERS(6) READERS(7) READERS(8)
static Reader readers[2][8]={{p1,p2,p3,p4,p5,p6,p7,p8},{a1,a2,a3,a4,a5,a6,a7,a8}};

/* Extract a complete group of lanes, without materializing byte elements. */
static inline uint64_t group(const Array *a, size_t i, unsigned b, unsigned lanes) {
    size_t pos=a->start+i;
    if(a->aligned) {
        size_t w=pos/(64/b); unsigned s=(pos%(64/b))*b;
        uint64_t x=a->data[w]>>s;
        unsigned available=(64/b)*b-s;
        if(lanes*b>available) x |= a->data[w+1]<<available;
        return x;
    }
    pos*=b;
    size_t w=pos>>6; unsigned s=pos&63;
    uint64_t x=a->data[w]>>s;
    if(s+lanes*b>64) x |= a->data[w+1]<<(64-s);
    return x;
}

#define BULK(B) \
static Py_ssize_t count##B(const Array *a, uint8_t value) { \
    const unsigned lanes=64/(B); \
    uint64_t low=0,high=0,rep=0; \
    for(unsigned j=0;j<lanes;j++) { \
        low |= ((1ull<<((B)-1))-1)<<(j*(B)); \
        high |= 1ull<<(j*(B)+(B)-1); rep |= (uint64_t)value<<(j*(B)); \
    } \
    Py_ssize_t total=0,i=0; \
    if(a->aligned || 64%(B)==0) { \
        while(i<a->length && (a->start+i)%lanes) { total+=(a->aligned?a##B(a,i):p##B(a,i))==value; i++; } \
        size_t w=(a->start+i)/lanes; \
        for(;a->length-i>=lanes;i+=lanes,w++) { \
            uint64_t x=a->data[w]^rep; \
            total+=__builtin_popcountll(~(((x&low)+low)|x|low)&high); \
        } \
    } else { \
        while(i<a->length && (a->start+i)%8) { total+=p##B(a,i)==value; i++; } \
        const uint64_t mask8=UINT64_MAX>>(64-8*(B)); \
        uint64_t l8=low&mask8,h8=high&mask8,r8=rep&mask8; \
        for(;a->length-i>=72;i+=64) { \
            const uint8_t *src=(const uint8_t *)a->data+(a->start+i)*(B)/8; \
            for(unsigned j=0;j<8;j++) { \
                uint64_t x; memcpy(&x,src+j*(B),8); x^=r8; \
                total+=__builtin_popcountll(~(((x&l8)+l8)|x|l8)&h8); \
            } \
        } \
    } \
    for(;a->length-i>=lanes;i+=lanes) { \
        uint64_t x=group(a,i,B,lanes)^rep; \
        uint64_t zero=~(((x&low)+low)|x|low)&high; \
        total+=__builtin_popcountll(zero); \
    } \
    for(;i<a->length;i++) total+=(a->aligned?a##B(a,i):p##B(a,i))==value; \
    return total; \
} \
static void unpack##B(const Array *a, uint8_t *dst) { \
    Py_ssize_t i=0; const unsigned lanes=64/(B); \
    for(;a->length-i>=lanes;i+=lanes) { \
        uint64_t x=group(a,i,B,lanes); \
        for(unsigned j=0;j<lanes;j++) dst[i+j]=(x>>(j*(B)))&((1u<<(B))-1); \
    } \
    for(;i<a->length;i++) dst[i]=a->aligned?a##B(a,i):p##B(a,i); \
}
BULK(1) BULK(2) BULK(3) BULK(4) BULK(5) BULK(6) BULK(7) BULK(8)
static Py_ssize_t (*counters[8])(const Array *,uint8_t)={count1,count2,count3,count4,count5,count6,count7,count8};
static void (*unpackers[8])(const Array *,uint8_t *)={unpack1,unpack2,unpack3,unpack4,unpack5,unpack6,unpack7,unpack8};

#define PACK(B) \
static int pack##B(Array *a,const uint8_t *src) { \
    const unsigned lanes=64/(B); Py_ssize_t i=0; \
    for(;a->length-i>=lanes;i+=lanes) { \
        uint64_t x=0; unsigned invalid=0; \
        for(unsigned j=0;j<lanes;j++) { x|=(uint64_t)src[i+j]<<(j*(B)); invalid|=src[i+j]; } \
        if(invalid>>B) return -1; \
        if(a->aligned) a->data[i/lanes]=x; \
        else { size_t pos=(size_t)i*(B); unsigned s=pos&63; a->data[pos>>6]|=x<<s; \
            if(s+lanes*(B)>64) a->data[(pos>>6)+1]|=x>>(64-s); } \
    } \
    for(;i<a->length;i++) { \
        if(src[i]>>B) return -1; \
        size_t pos=a->aligned?(size_t)(i/lanes)*64+(i%lanes)*(B):(size_t)i*(B); \
        unsigned s=pos&63; a->data[pos>>6]|=(uint64_t)src[i]<<s; \
        if(s+(B)>64) a->data[(pos>>6)+1]|=(uint64_t)src[i]>>(64-s); \
    } return 0; \
}
PACK(1) PACK(2) PACK(3) PACK(4) PACK(5) PACK(6) PACK(7) PACK(8)
static int (*packers[8])(Array *,const uint8_t *)={pack1,pack2,pack3,pack4,pack5,pack6,pack7,pack8};

/* Short needles: reject whole words by their first symbol before full matching. */
#define FIND(B) \
static Py_ssize_t find##B(const Array *a,const uint8_t *p,unsigned n) { \
    const unsigned lanes=64/(B); uint64_t low=0,high=0,rep=0,needle=0; \
    for(unsigned j=0;j<lanes;j++) { low|=((1ull<<((B)-1))-1)<<(j*(B)); high|=1ull<<(j*(B)+(B)-1); rep|=(uint64_t)p[0]<<(j*(B)); } \
    for(unsigned j=0;j<n;j++) { if(p[j]>>(B)) return -1; needle|=(uint64_t)p[j]<<(j*(B)); } \
    uint64_t mask=n*(B)==64?UINT64_MAX:(1ull<<(n*(B)))-1; Py_ssize_t i=0,last=a->length-n; \
    for(;a->length-i>=lanes && i<=last;i+=lanes) { \
        uint64_t x=group(a,i,B,lanes)^rep; uint64_t candidates=~(((x&low)+low)|x|low)&high; \
        while(candidates) { unsigned j=__builtin_ctzll(candidates)/(B); Py_ssize_t at=i+j; \
            if(at>last) return -1; \
            if((group(a,at,B,n)&mask)==needle) return at; candidates&=candidates-1; } \
    } \
    for(;i<=last;i++) if((group(a,i,B,n)&mask)==needle) return i; return -1; \
}
FIND(1) FIND(2) FIND(3) FIND(4) FIND(5) FIND(6) FIND(7) FIND(8)
static Py_ssize_t (*finders[8])(const Array *,const uint8_t *,unsigned)={find1,find2,find3,find4,find5,find6,find7,find8};

static void put(Array *a, size_t i, uint8_t value) {
    size_t pos=a->start+i, w; unsigned s, b=a->bits;
    if (a->aligned) { w=pos/(64/b); s=(pos%(64/b))*b; }
    else { pos*=b; w=pos>>6; s=pos&63; }
    uint64_t mask=(1u<<b)-1;
    a->data[w]=(a->data[w] & ~(mask<<s)) | ((uint64_t)value<<s);
    if (s+b>64) {
        unsigned spill=s+b-64;
        a->data[w+1]=(a->data[w+1] & ~((1ull<<spill)-1)) | ((uint64_t)value>>(64-s));
    }
}
static Array *allocate(Py_ssize_t n, unsigned bits, unsigned aligned) {
    if (n<0 || (size_t)n > (SIZE_MAX-63)/bits) { PyErr_NoMemory(); return NULL; }
    size_t words=aligned ? (size_t)n/(64/bits)+((size_t)n%(64/bits)!=0) : ((size_t)n*bits+63)/64;
    if (words > (size_t)PY_SSIZE_T_MAX/8) { PyErr_NoMemory(); return NULL; }
    Array *a=PyObject_New(Array,&ArrayType);
    if (!a) return NULL;
    a->data=NULL; a->owner=NULL; a->start=0; a->length=n;
    a->bits=bits; a->aligned=aligned; a->words=words; a->read=readers[aligned][bits-1];
    a->data=PyMem_Calloc(words ? words : 1,8);
    if (!a->data) { Py_DECREF(a); PyErr_NoMemory(); return NULL; }
    return a;
}
static int value_of(PyObject *obj, unsigned bits, uint8_t *out) {
    PyObject *idx=PyNumber_Index(obj);
    if (!idx) return -1;
    long v=PyLong_AsLong(idx); Py_DECREF(idx);
    if (v==-1 && PyErr_Occurred()) return -1;
    if (v<0 || v>=(1l<<bits)) { PyErr_SetString(PyExc_ValueError,"value outside bit width"); return -1; }
    *out=(uint8_t)v; return 0;
}
static PyObject *array_new(PyTypeObject *type, PyObject *args, PyObject *kwargs) {
    PyObject *values; int bits=8; const char *layout="packed";
    static char *names[]={"values","bits","layout",NULL};
    if (!PyArg_ParseTupleAndKeywords(args,kwargs,"O|is:Array",names,&values,&bits,&layout)) return NULL;
    if (bits<1 || bits>8) { PyErr_SetString(PyExc_ValueError,"bits must be between 1 and 8"); return NULL; }
    unsigned aligned;
    if (!strcmp(layout,"packed")) aligned=0;
    else if (!strcmp(layout,"word-aligned")) aligned=1;
    else { PyErr_SetString(PyExc_ValueError,"layout must be packed or word-aligned"); return NULL; }
    Py_buffer buf;
    if (PyObject_CheckBuffer(values) && PyObject_GetBuffer(values,&buf,PyBUF_FORMAT|PyBUF_ND)==0) {
        if (buf.ndim==1 && buf.itemsize==1 && buf.format && !strcmp(buf.format,"B")) {
            Array *a=allocate(buf.len,bits,aligned);
            if (a) {
                if(bits==8) memcpy(a->data,buf.buf,buf.len);
                else if(packers[bits-1](a,buf.buf)<0) {
                    PyErr_SetString(PyExc_ValueError,"value outside bit width"); Py_DECREF(a); a=NULL;
                }
            }
            PyBuffer_Release(&buf); return (PyObject *)a;
        }
        PyBuffer_Release(&buf);
    } else if (PyErr_Occurred()) PyErr_Clear();
    /* A user-defined __index__ can resize an input list: hold a snapshot. */
    PyObject *seq=PySequence_Tuple(values);
    if (!seq) return NULL;
    Py_ssize_t n=PySequence_Fast_GET_SIZE(seq);
    Array *a=allocate(n,bits,aligned);
    if (a) for (Py_ssize_t i=0;i<n;i++) {
        uint8_t v;
        if (value_of(PySequence_Fast_GET_ITEM(seq,i),bits,&v)<0) { Py_DECREF(a); a=NULL; break; }
        put(a,i,v);
    }
    Py_DECREF(seq); return (PyObject *)a;
}
static void array_dealloc(Array *a) {
    if (a->owner) Py_DECREF(a->owner); else PyMem_Free(a->data);
    PyObject_Del(a);
}
static Py_ssize_t array_len(Array *a) { return a->length; }
static int normalize(Array *a, Py_ssize_t *i) {
    if (*i<0) *i+=a->length;
    if (*i<0 || *i>=a->length) { PyErr_SetString(PyExc_IndexError,"array index out of range"); return -1; }
    return 0;
}
static PyObject *array_item(Array *a, Py_ssize_t i) {
    if (normalize(a,&i)<0) return NULL;
    return PyLong_FromLong(a->read(a,i));
}
static Array *view(Array *a, Py_ssize_t start, Py_ssize_t n) {
    Array *v=PyObject_New(Array,&ArrayType);
    if (!v) return NULL;
    v->data=a->data; v->length=n; v->start=a->start+start;
    v->words=0; v->bits=a->bits; v->aligned=a->aligned; v->read=a->read;
    v->owner=a->owner ? a->owner : (PyObject *)a; Py_INCREF(v->owner);
    return v;
}
static PyObject *array_subscript(Array *a, PyObject *key) {
    if (PyIndex_Check(key)) {
        Py_ssize_t i=PyNumber_AsSsize_t(key,PyExc_IndexError);
        if (i==-1 && PyErr_Occurred()) return NULL;
        return array_item(a,i);
    }
    if (PySlice_Check(key)) {
        Py_ssize_t start,stop,step,n;
        if (PySlice_Unpack(key,&start,&stop,&step)<0) return NULL;
        n=PySlice_AdjustIndices(a->length,&start,&stop,step);
        if (step==1) return (PyObject *)view(a,start,n);
        Array *out=allocate(n,a->bits,a->aligned);
        if (!out) return NULL;
        for (Py_ssize_t j=0,i=start;j<n;j++) { put(out,j,a->read(a,i)); if(j+1<n) i+=step; }
        return (PyObject *)out;
    }
    PyErr_SetString(PyExc_TypeError,"index must be an integer or slice"); return NULL;
}
static int array_assign(Array *a, PyObject *key, PyObject *value) {
    if (!value) { PyErr_SetString(PyExc_TypeError,"fixed-size array does not support deletion"); return -1; }
    if (!PyIndex_Check(key)) { PyErr_SetString(PyExc_TypeError,"only scalar assignment is supported"); return -1; }
    Py_ssize_t i=PyNumber_AsSsize_t(key,PyExc_IndexError);
    if (i==-1 && PyErr_Occurred()) return -1;
    if (normalize(a,&i)<0) return -1;
    uint8_t v; if(value_of(value,a->bits,&v)<0) return -1;
    put(a,i,v); return 0;
}
static PyObject *array_bytes(Array *a, PyObject *unused) {
    PyObject *out=PyBytes_FromStringAndSize(NULL,a->length);
    if (!out) return NULL;
    uint8_t *dst=(uint8_t *)PyBytes_AS_STRING(out);
    if(a->bits==8) memcpy(dst,(uint8_t *)a->data+a->start,a->length);
    else unpackers[a->bits-1](a,dst);
    return out;
}
static PyObject *array_list(Array *a, PyObject *unused) {
    PyObject *out=PyList_New(a->length);
    if (!out) return NULL;
    for (Py_ssize_t i=0;i<a->length;i++) {
        PyObject *v=PyLong_FromLong(a->read(a,i));
        if (!v) { Py_DECREF(out); return NULL; }
        PyList_SET_ITEM(out,i,v);
    }
    return out;
}
static PyObject *array_copy(Array *a, PyObject *unused) {
    Array *out=allocate(a->length,a->bits,a->aligned);
    if (!out) return NULL;
    if(!a->aligned) {
        size_t pos=a->start*a->bits, w=pos>>6; unsigned s=pos&63;
        size_t remaining=(size_t)a->length*a->bits;
        if(s==0 && out->words) {
            memcpy(out->data,a->data+w,out->words*8);
            unsigned tail=remaining&63;
            if(tail) out->data[out->words-1]&=(1ull<<tail)-1;
        } else for(size_t j=0;j<out->words;j++) {
            unsigned take=remaining>=64?64:(unsigned)remaining;
            uint64_t x=a->data[w+j]>>s;
            if(s+take>64) x|=a->data[w+j+1]<<(64-s);
            out->data[j]=take==64?x:x&((1ull<<take)-1);
            remaining-=take;
        }
    } else {
        unsigned lanes=64/a->bits; Py_ssize_t i=0;
        uint64_t mask=lanes*a->bits==64?UINT64_MAX:(1ull<<(lanes*a->bits))-1;
        if(a->start%lanes==0) {
            size_t full=(size_t)a->length/lanes;
            memcpy(out->data,a->data+a->start/lanes,full*8);
            i=full*lanes;
        } else for(;a->length-i>=lanes;i+=lanes) out->data[i/lanes]=group(a,i,a->bits,lanes)&mask;
        for(;i<a->length;i++) put(out,i,a->read(a,i));
    }
    return (PyObject *)out;
}
static PyObject *array_gather(Array *a, PyObject *indices) {
    PyObject *seq=PySequence_Tuple(indices);
    if (!seq) return NULL;
    Py_ssize_t n=PySequence_Fast_GET_SIZE(seq);
    Array *out=allocate(n,a->bits,a->aligned);
    if (out) for(Py_ssize_t j=0;j<n;j++) {
        Py_ssize_t i=PyNumber_AsSsize_t(PySequence_Fast_GET_ITEM(seq,j),PyExc_IndexError);
        if ((i==-1 && PyErr_Occurred()) || normalize(a,&i)<0) { Py_DECREF(out); out=NULL; break; }
        put(out,j,a->read(a,i));
    }
    Py_DECREF(seq); return (PyObject *)out;
}
static PyObject *array_count(Array *a, PyObject *obj) {
    uint8_t value;
    if(value_of(obj,a->bits,&value)<0) {
        if(PyErr_ExceptionMatches(PyExc_ValueError)||PyErr_ExceptionMatches(PyExc_OverflowError)) { PyErr_Clear(); return PyLong_FromLong(0); }
        return NULL;
    }
    Py_ssize_t count=counters[a->bits-1](a,value);
    return PyLong_FromSsize_t(count);
}
static PyObject *array_find(Array *a, PyObject *obj) {
    PyObject *needle;
    if (PyObject_TypeCheck(obj,&ArrayType)) needle=array_bytes((Array *)obj,NULL);
    else {
        PyObject *args=Py_BuildValue("Oi",obj,a->bits);
        if(!args) return NULL;
        PyObject *tmp=array_new(&ArrayType,args,NULL); Py_DECREF(args);
        if(!tmp) return NULL;
        needle=array_bytes((Array *)tmp,NULL); Py_DECREF(tmp);
    }
    if(!needle) return NULL;
    Py_ssize_t n=PyBytes_GET_SIZE(needle);
    if(!n) { Py_DECREF(needle); return PyLong_FromLong(0); }
    if(n>a->length) { Py_DECREF(needle); return PyLong_FromLong(-1); }
    if(n<=64/a->bits) {
        Py_ssize_t result=finders[a->bits-1](a,(uint8_t *)PyBytes_AS_STRING(needle),n);
        Py_DECREF(needle); return PyLong_FromSsize_t(result);
    }
    if((size_t)n>SIZE_MAX/sizeof(Py_ssize_t)) { Py_DECREF(needle); return PyErr_NoMemory(); }
    Py_ssize_t *prefix=PyMem_Calloc(n,sizeof(Py_ssize_t));
    if(!prefix) { Py_DECREF(needle); return PyErr_NoMemory(); }
    uint8_t *p=(uint8_t *)PyBytes_AS_STRING(needle);
    for(Py_ssize_t i=1,j=0;i<n;i++) {
        while(j && p[i]!=p[j]) j=prefix[j-1];
        if(p[i]==p[j]) j++;
        prefix[i]=j;
    }
    Py_ssize_t result=-1;
    for(Py_ssize_t i=0,j=0;i<a->length;i++) {
        uint8_t c=a->read(a,i);
        while(j && c!=p[j]) j=prefix[j-1];
        if(c==p[j]) j++;
        if(j==n) { result=i-n+1; break; }
    }
    PyMem_Free(prefix); Py_DECREF(needle); return PyLong_FromSsize_t(result);
}
static PyObject *array_compare(PyObject *left, PyObject *right, int op) {
    if(!PyObject_TypeCheck(right,&ArrayType)) Py_RETURN_NOTIMPLEMENTED;
    Array *a=(Array *)left,*b=(Array *)right;
    if(op==Py_EQ || op==Py_NE) {
        int equal=a->length==b->length;
        if(equal && a->bits==b->bits) {
            unsigned lanes=64/a->bits;
            uint64_t mask=lanes*a->bits==64?UINT64_MAX:(1ull<<(lanes*a->bits))-1;
            Py_ssize_t i=0;
            if(a->aligned==b->aligned && a->aligned && a->start%lanes==0 && b->start%lanes==0) {
                size_t full=(size_t)a->length/lanes;
                equal=memcmp(a->data+a->start/lanes,b->data+b->start/lanes,full*8)==0;
                i=full*lanes;
            } else if(!a->aligned && !b->aligned && (a->start*a->bits)%8==0 && (b->start*b->bits)%8==0) {
                size_t bytes=(size_t)a->length*a->bits/8;
                equal=memcmp((uint8_t *)a->data+a->start*a->bits/8,(uint8_t *)b->data+b->start*b->bits/8,bytes)==0;
                i=bytes*8/a->bits;
            }
            for(;equal && a->length-i>=lanes;i+=lanes) {
                if((group(a,i,a->bits,lanes)^group(b,i,b->bits,lanes))&mask) { equal=0; break; }
            }
            if(equal) for(;i<a->length;i++) if(a->read(a,i)!=b->read(b,i)) { equal=0; break; }
        } else if(equal) {
            for(Py_ssize_t i=0;i<a->length;i++) if(a->read(a,i)!=b->read(b,i)) { equal=0; break; }
        }
        return PyBool_FromLong(op==Py_EQ?equal:!equal);
    }
    Py_ssize_t n=a->length<b->length?a->length:b->length;
    int cmp=0;
    for(Py_ssize_t i=0;i<n;i++) {
        int x=a->read(a,i),y=b->read(b,i);
        if(x!=y) { cmp=x<y?-1:1; break; }
    }
    if(!cmp) cmp=(a->length>b->length)-(a->length<b->length);
    int result=op==Py_EQ?cmp==0:op==Py_NE?cmp!=0:op==Py_LT?cmp<0:op==Py_LE?cmp<=0:op==Py_GT?cmp>0:cmp>=0;
    return PyBool_FromLong(result);
}
static PyObject *array_sizeof(Array *a, PyObject *unused) { return PyLong_FromSize_t(sizeof(Array)+(a->owner?0:(a->words?a->words:1)*8)); }
static PyObject *get_bits(Array *a, void *c) { return PyLong_FromLong(a->bits); }
static PyObject *get_layout(Array *a, void *c) { return PyUnicode_FromString(a->aligned?"word-aligned":"packed"); }
static PyObject *get_nbytes(Array *a, void *c) { return PyLong_FromSize_t(a->owner?0:(a->words?a->words:1)*8); }
static PyObject *get_base(Array *a, void *c) { PyObject *base=a->owner?a->owner:Py_None; Py_INCREF(base); return base; }
static PyMethodDef methods[]={
    {"tobytes",(PyCFunction)array_bytes,METH_NOARGS,"Return unpacked unsigned bytes."},
    {"tolist",(PyCFunction)array_list,METH_NOARGS,"Return a list of integers."},
    {"copy",(PyCFunction)array_copy,METH_NOARGS,"Return an independent array."},
    {"gather",(PyCFunction)array_gather,METH_O,"Copy indexed values into an array."},
    {"count",(PyCFunction)array_count,METH_O,"Count occurrences of an integer."},
    {"find",(PyCFunction)array_find,METH_O,"Find a subsequence; return -1 when absent."},
    {"__sizeof__",(PyCFunction)array_sizeof,METH_NOARGS,"Object and owned allocation bytes."},
    {NULL,NULL,0,NULL}
};
static PyGetSetDef getters[]={
    {"bits",(getter)get_bits,NULL,NULL,NULL}, {"layout",(getter)get_layout,NULL,NULL,NULL},
    {"nbytes",(getter)get_nbytes,NULL,"Owned buffer bytes (zero for views).",NULL},
    {"base",(getter)get_base,NULL,"Root owner of a view, or None.",NULL}, {NULL,NULL,NULL,NULL,NULL}
};
static PySequenceMethods sequence={.sq_length=(lenfunc)array_len,.sq_item=(ssizeargfunc)array_item};
static PyMappingMethods mapping={.mp_length=(lenfunc)array_len,.mp_subscript=(binaryfunc)array_subscript,.mp_ass_subscript=(objobjargproc)array_assign};
static PyTypeObject ArrayType={
    PyVarObject_HEAD_INIT(NULL,0)
    .tp_name="tightarray.Array",.tp_basicsize=sizeof(Array),.tp_dealloc=(destructor)array_dealloc,
    .tp_flags=Py_TPFLAGS_DEFAULT,.tp_doc="Fixed-size mutable unsigned small-integer array.",
    .tp_new=array_new,.tp_as_sequence=&sequence,.tp_as_mapping=&mapping,
    .tp_methods=methods,.tp_getset=getters,.tp_richcompare=array_compare,.tp_hash=PyObject_HashNotImplemented
};
#include "_rows.h"
static PyModuleDef module={PyModuleDef_HEAD_INIT,.m_name="_core",.m_size=-1};
PyMODINIT_FUNC PyInit__core(void) {
    if(PyType_Ready(&ArrayType)<0) return NULL;
    PyObject *m=PyModule_Create(&module); if(!m) return NULL;
    Py_INCREF(&ArrayType);
    if(PyModule_AddObject(m,"Array",(PyObject *)&ArrayType)<0) { Py_DECREF(&ArrayType); Py_DECREF(m); return NULL; }
    if(PyType_Ready(&RowsType)<0) { Py_DECREF(m); return NULL; }
    Py_INCREF(&RowsType);
    if(PyModule_AddObject(m,"_Rows",(PyObject *)&RowsType)<0) { Py_DECREF(&RowsType); Py_DECREF(m); return NULL; }
    return m;
}
