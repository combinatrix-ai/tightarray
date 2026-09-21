# Exact-bytes ingestion experiment

This benchmark-only experiment adds `if type(values) is bytes: return values` before the existing `_values` buffer probe. It changes no production source or live module globals. Two temporary modules execute pinned `ae5c4ff` Python source with the same current native extension; the only Python difference is that inserted branch. This intentionally isolates ingestion copying from subsequent changes to bulk-write dispatch.

Exact built-in bytes are immutable and already contain valid uint8 elements. Returning them preserves values and avoids a memoryview allocation and byte copy. Bytes subclasses retain the existing buffer path, including its precedence over a custom iterator. Bytearray and memoryview inputs still copy into independent bytes. Signed/wide/strided buffers and general iterables preserve their original validation and logical-element behavior. Eleven focused tests cover these contracts without requiring historical Git commits.

The paired microbenchmark uses byte lengths 1, 16, 64, 256, and 4,096, each as bytes, bytearray, memoryview, or list. Input preparation is outside timing. Seven repeats alternate policy order using a fixed random seed. The bulk-write control performs 256 writes to one warm ordinary or structural-span chunk, followed by one flush, with no codec. The first write changes values; subsequent writes repeat that payload. It is a focused ingestion/dispatch workload, not a simulation or application E2E benchmark.

Run:

```sh
python -m benchmarks.compressed_values_bytes --output docs/compressed-values-bytes-results.json
```

The JSON records all samples, pinned Python source hash, and before/after hashes for the benchmark, live Python source, C headers, and loaded extension. Fallback regressions must be considered alongside bytes gains before adoption.

## Results

Median nanoseconds per operation for exact bytes:

| Operation | Bytes | Baseline | Candidate | Reduction |
|---|---:|---:|---:|---:|
| values  | 1 | 172.2 | 37.0 | 78.5% |
| values  | 16 | 172.6 | 36.7 | 78.7% |
| values  | 64 | 170.4 | 36.7 | 78.4% |
| values  | 256 | 177.0 | 36.3 | 79.5% |
| values  | 4096 | 280.8 | 40.3 | 85.6% |
| write-flush ordinary | 1 | 4134.6 | 3971.4 | 3.9% |
| write-flush ordinary | 16 | 4122.1 | 3939.0 | 4.4% |
| write-flush ordinary | 64 | 4088.4 | 3937.5 | 3.7% |
| write-flush ordinary | 256 | 4227.9 | 4031.1 | 4.7% |
| write-flush span | 1 | 842.0 | 680.0 | 19.2% |
| write-flush span | 16 | 843.4 | 696.0 | 17.5% |
| write-flush span | 64 | 974.4 | 828.1 | 15.0% |
| write-flush span | 256 | 1410.5 | 1245.3 | 11.7% |

The ingestion helper improves 4.6–7.0× for exact bytes. This saves roughly 135–241 ns per call, rather than making the surrounding operation that many times faster. Paired write-plus-flush improves 3.7–4.7% for ordinary chunks and 11.7–19.2% for spans under the pinned Python dispatch policy.

The extra type branch has a measurable fallback cost: bytearray and memoryview helper calls are approximately 3–7% slower; lists range from a 1.5% gain to a 1.6% loss. In complete write-plus-flush controls, most non-bytes differences lie within roughly ±2.4%, with one span/16-byte bytearray result 3.7% faster, consistent with noise rather than a new fallback mechanism. The study supports a small exact-bytes optimization, with its input-dependent cost stated explicitly. It does not establish current-head application throughput: pinned Python predates the ordinary native bulk-write integration, while native helpers are shared between policies.

All 52 configurations × seven repeats passed result equality and source guards. Eleven validation tests passed. Full samples and hashes: [raw results](compressed-values-bytes-results.json).
