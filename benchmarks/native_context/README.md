# Experimental compression-only C context

This is a disposable experiment, not a production extension or packaging contract. It compiles against the header and shared library shipped in the installed Python Blosc2 wheel. It uses only public `blosc2_create_cctx`, `blosc2_compress_ctx`, and `blosc2_free_ctx`; no SChunk, decoder context, private prefilter API, ctypes layout, or stored compressed chunk is involved.

`CompressionContext(codec, length, shuffle)` pins one payload length and the parameters used by the current Python baseline: LZ4/ZSTD, level5, typesize1, nthreads1, AUTO_SPLIT, and a single NOFILTER/BITSHUFFLE at filter position zero. Fixed length avoids introducing cross-size context-history behavior. `compress(exact_bytes)` keeps the GIL throughout, returns independent bytes, and allocates length+MAX_OVERHEAD before copying the actual compressed length. This deliberately does not combine reusable contexts with a bounded destination experiment. A native compression error retires the context; validation errors leave it usable. `close()` is idempotent, and destruction also frees the context. The module explicitly initializes its independent shared-library image once, and never calls global destroy. Every context is still individually freed. See the packaging limitation below.

Build and verify using the current disposable CPython environment:

```sh
/tmp/ta-cap-env/bin/python benchmarks/native_context/build.py build_ext \
  --build-temp /tmp/ta-ccontext-objects --build-lib /tmp/ta-ccontext-lib
PYTHONPATH=/tmp/ta-ccontext-lib /tmp/ta-cap-env/bin/python -m pytest -q \
  benchmarks/native_context/test_context.py
```

Verified 37 tests passed with installed Blosc2 4.13.1. They compare exact bytes against public compress2 and decompress them for both codecs/filters, lengths0/1/7/31/64/255/4093/4096/16385, and changing input alphabets within each context. They also cover parameter/input validation, repeated close, bytes surviving context destruction, and same-context calls from multiple Python threads serialized by the GIL. No performance or RSS conclusion has been measured yet.

The linked image reports `@rpath/libblosc2.9.dylib`; build.py adds the installed wheel's lib directory as an rpath. This local build is not portable packaging: distribution would require deliberate dependency discovery, ABI/library-version compatibility, platform wheel testing, and optional-dependency behavior. Opaque codec workspace remains allocated until close/free and has no reliable public byte-accounting API here. A context count bounds object count, not native scratch bytes or RSS. Python validation covers normal errors; native codec allocation/compression failures have not been fault-injected. Full safety validation would also include sanitizers and target-specific library lifecycle tests before production adoption.


## Independent library image: packaging and measurement limitation

`otool -L` on installed `blosc2/blosc2_ext.abi3.so` lists only Accelerate and libSystem, while this prototype links `libblosc2.9.dylib`. `nm -gU` exposes none of the required Blosc context symbols from the Python extension. Thus this wheel statically embeds a hidden Blosc copy and the experiment loads a second library image. The prototype now explicitly initializes that second image once and retains global library state for process lifetime. The 37 tests were rerun successfully after this fix. They establish sampled byte equivalence, not production packaging suitability. This is not a production candidate as packaged. Any future RSS comparison must consistently import the prototype in all arms or explicitly include the extra library image in measured overhead; neither approach equates opaque workspace to a byte-bounded cache.


Verified local linkage paths:

- Python extension: `/tmp/ta-cap-env/lib/python3.12/site-packages/blosc2/blosc2_ext.abi3.so`; dependent images are Accelerate and libSystem, with no libblosc2 dependency.
- Prototype: `/tmp/ta-ccontext-lib/ta_ccontext.cpython-312-darwin.so`; dependency `@rpath/libblosc2.9.dylib`, rpath `/tmp/ta-cap-env/lib/python3.12/site-packages/blosc2/lib`.
- `nm -gU` on the Python extension does not expose `blosc2_create_cctx`, `blosc2_compress_ctx`, or `blosc2_free_ctx`; the prototype does not attempt to access hidden/private symbols.
