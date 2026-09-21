/* Exact modal default and the minimal nondefault span. Ties choose lowest byte.
 * Uniform and empty inputs use an empty span (0,0); empty default is zero.
 * Every counter is at most input length, so Py_ssize_t increments cannot wrap. */
static PyObject *compressed_byte_trim(PyObject *module,PyObject *raw) {
    if(!PyBytes_Check(raw)) { PyErr_SetString(PyExc_TypeError,"raw must be bytes"); return NULL; }
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    Py_ssize_t length=PyBytes_GET_SIZE(raw), counts[256]={0};
    for(Py_ssize_t i=0;i<length;i++) counts[src[i]]++;
    unsigned mode=0;
    for(unsigned value=1;value<256;value++) if(counts[value]>counts[mode]) mode=value;
    Py_ssize_t first=0,last=length;
    while(first<length && src[first]==mode) first++;
    if(first==length) first=last=0;
    else while(last>first && src[last-1]==mode) last--;
    return Py_BuildValue("inn",(int)mode,first,last);
}

/* Any default different from both endpoints omits no edge and cannot beat
 * the corresponding untrimmed representation with its smaller header.
 * Enumerate only the endpoint defaults; selection still compares full cost. */
static PyObject *compressed_byte_edge_spans(PyObject *module,PyObject *raw) {
    if(!PyBytes_Check(raw)) { PyErr_SetString(PyExc_TypeError,"raw must be bytes"); return NULL; }
    Py_ssize_t length=PyBytes_GET_SIZE(raw);
    if(!length) return PyTuple_New(0);
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    unsigned left=src[0],right=src[length-1];
    Py_ssize_t first=1;
    while(first<length && src[first]==left) first++;
    if(first==length) return Py_BuildValue("((inn))",(int)left,(Py_ssize_t)0,(Py_ssize_t)0);
    Py_ssize_t last=length-1;
    while(last>0 && src[last-1]==right) last--;
    if(left==right) return Py_BuildValue("((inn))",(int)left,first,last);
    return Py_BuildValue("((inn)(inn))",(int)left,first,length,(int)right,(Py_ssize_t)0,last);
}

static unsigned compressed_trim_bits(unsigned maximum) {
    unsigned bits=1;
    while(maximum>>bits) bits++;
    return bits;
}
/* Private planner: colors must describe the complete raw alphabet. We validate
 * its shape/order, not completeness, to avoid a second whole-input scan. Wrong
 * metadata can prune candidates but cannot affect memory bounds. Input length
 * is capped65535 before any packed-size multiplication. */
static PyObject *compressed_trim_plan(PyObject *module,PyObject *args) {
    PyObject *raw,*colors,*enabled; Py_ssize_t limit;
    if(!PyArg_ParseTuple(args,"OOOn:_trim_plan",&raw,&colors,&enabled,&limit)) return NULL;
    if(!PyBytes_Check(raw) || !PyBytes_Check(colors)) { PyErr_SetString(PyExc_TypeError,"raw and colors must be bytes"); return NULL; }
    if(!PyBool_Check(enabled)) { PyErr_SetString(PyExc_TypeError,"palette_enabled must be bool"); return NULL; }
    Py_ssize_t count=PyBytes_GET_SIZE(colors), length=PyBytes_GET_SIZE(raw);
    if(count>256) { PyErr_SetString(PyExc_ValueError,"colors must be sorted unique bytes"); return NULL; }
    const uint8_t *alphabet=(const uint8_t *)PyBytes_AS_STRING(colors);
    for(Py_ssize_t i=1;i<count;i++) if(alphabet[i]<=alphabet[i-1]) {
        PyErr_SetString(PyExc_ValueError,"colors must be sorted unique bytes"); return NULL;
    }
    if(length==0 || length>65535 || limit<=16 || count<2) Py_RETURN_NONE;
    const uint8_t *src=(const uint8_t *)PyBytes_AS_STRING(raw);
    unsigned left=src[0],right=src[length-1];
    Py_ssize_t leading=1,trailing=length-1;
    while(leading<length && src[leading]==left) leading++;
    if(leading==length) Py_RETURN_NONE;
    while(trailing>0 && src[trailing-1]==right) trailing--;
    int found=0; unsigned winner_value=0,winner_bits=0;
    Py_ssize_t winner_first=0,winner_last=0,winner_count=0;
    uint8_t winner_palette[256];
    for(unsigned candidate=0;candidate<(left==right?1u:2u);candidate++) {
        unsigned value=candidate?right:left;
        Py_ssize_t first=candidate?0:leading;
        Py_ssize_t last=(candidate || left==right)?trailing:length;
        if(first==0 && last==length) continue;
        Py_ssize_t span=last-first;
        unsigned maximum=alphabet[count-1]==value?alphabet[count-2]:alphabet[count-1];
        Py_ssize_t lower=((span*compressed_trim_bits(maximum)+63)/64)*8;
        if(enabled==Py_True) {
            Py_ssize_t palette_lower=count-1+((span*compressed_trim_bits((unsigned)count-2)+63)/64)*8;
            if(palette_lower<lower) lower=palette_lower;
        }
        if(8+lower>=limit) continue;
        /* The omitted edges contain only value, so every other global color
         * must remain inside. Reuse the trusted complete alphabet; only the
         * presence of value needs checking, and memchr can stop at its first
         * occurrence. This also preserves sorted palette/tie ordering. */
        uint8_t span_colors[256]; unsigned span_count=0;
        if(memchr(src+first,(int)value,(size_t)span)) {
            span_count=(unsigned)count;
            memcpy(span_colors,alphabet,(size_t)count);
        } else {
            for(Py_ssize_t i=0;i<count;i++)
                if(alphabet[i]!=value) span_colors[span_count++]=alphabet[i];
        }
        if(!span_count) continue;
        unsigned bits=compressed_trim_bits(span_colors[span_count-1]);
        Py_ssize_t size=((span*bits+63)/64)*8, palette_count=0;
        if(enabled==Py_True && span_count<256) {
            unsigned palette_bits=compressed_trim_bits(span_count-1);
            Py_ssize_t palette_size=span_count+((span*palette_bits+63)/64)*8;
            if(palette_size<size) { size=palette_size; bits=palette_bits; palette_count=span_count; }
        }
        if(8+size<limit) {
            found=1; limit=8+size; winner_value=value; winner_first=first;
            winner_last=last; winner_bits=bits; winner_count=palette_count;
            if(palette_count) memcpy(winner_palette,span_colors,(size_t)palette_count);
        }
    }
    if(!found) Py_RETURN_NONE;
    PyObject *palette=PyBytes_FromStringAndSize((const char *)winner_palette,winner_count);
    if(!palette) return NULL;
    return Py_BuildValue("(inniNn)",(int)winner_value,winner_first,winner_last,(int)winner_bits,palette,limit);
}
