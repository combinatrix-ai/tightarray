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

After measurement, the harness injection was made idempotent so correctness tests remain valid once production adopts the same branch. Reinjection now preserves an existing exact `INSERTION + MARKER` sequence. The historical JSON and its original benchmark hash remain unchanged; the current harness hash therefore differs from the measured artifact. This maintenance change was not timed.

## Integrated ordinary-write measurement

A second paired run pins `ef925f5`, which includes the ordinary native bulk-write path, and inserts only the exact-bytes branch. It shares the frozen current native extension. This is a separate experiment, not a replacement of the historical result. The same 52 configurations and seven repeats pass equality and before/after source guards.

Median nanoseconds per write, including one flush per 256 writes:

| Layout | Input | Bytes | Baseline | Candidate | Change |
|---|---|---:|---:|---:|---:|
| ordinary | bytes | 1 | 800.3 | 685.2 | -14.4% |
| ordinary | bytearray | 1 | 793.3 | 803.4 | +1.3% |
| ordinary | memoryview | 1 | 773.3 | 781.6 | +1.1% |
| ordinary | list | 1 | 964.7 | 990.6 | +2.7% |
| ordinary | bytes | 16 | 890.1 | 675.1 | -24.2% |
| ordinary | bytearray | 16 | 819.2 | 829.4 | +1.3% |
| ordinary | memoryview | 16 | 790.9 | 800.6 | +1.2% |
| ordinary | list | 16 | 1055.5 | 1130.5 | +7.1% |
| ordinary | bytes | 64 | 939.8 | 790.2 | -15.9% |
| ordinary | bytearray | 64 | 973.8 | 956.7 | -1.8% |
| ordinary | memoryview | 64 | 931.0 | 945.1 | +1.5% |
| ordinary | list | 64 | 1368.2 | 1431.2 | +4.6% |
| ordinary | bytes | 256 | 1384.1 | 1214.5 | -12.3% |
| ordinary | bytearray | 256 | 1410.8 | 1377.3 | -2.4% |
| ordinary | memoryview | 256 | 1368.0 | 1343.9 | -1.8% |
| ordinary | list | 256 | 2404.5 | 2446.6 | +1.8% |
| span | bytes | 1 | 814.9 | 661.0 | -18.9% |
| span | bytearray | 1 | 812.0 | 821.6 | +1.2% |
| span | memoryview | 1 | 811.8 | 830.6 | +2.3% |
| span | list | 1 | 986.0 | 996.3 | +1.0% |
| span | bytes | 16 | 830.4 | 682.0 | -17.9% |
| span | bytearray | 16 | 839.2 | 852.1 | +1.5% |
| span | memoryview | 16 | 826.3 | 830.1 | +0.5% |
| span | list | 16 | 1078.3 | 1086.9 | +0.8% |
| span | bytes | 64 | 981.8 | 825.2 | -15.9% |
| span | bytearray | 64 | 968.4 | 971.5 | +0.3% |
| span | memoryview | 64 | 943.4 | 951.0 | +0.8% |
| span | list | 64 | 1356.6 | 1366.2 | +0.7% |
| span | bytes | 256 | 1374.8 | 1228.4 | -10.7% |
| span | bytearray | 256 | 1380.5 | 1387.0 | +0.5% |
| span | memoryview | 256 | 1356.0 | 1366.9 | +0.8% |
| span | list | 256 | 2371.9 | 2422.9 | +2.1% |

Exact bytes now reduce ordinary write-plus-flush time by 12.3–24.2% and span time by 10.6–18.9%. Once native writes remove the previous whole-chunk repacking cost, ingestion copying becomes a larger part of the operation.

Fallback costs remain visible: ordinary list writes regress 1.8–7.1%, with the largest regression at 16 bytes and 4.6% at 64 bytes. Bytearray/memoryview complete-write controls range roughly from a 2.4% gain to a 2.3% loss. Ingestion-only bytearray/memoryview costs rise 2–8%; the one-element list rises 5.5%, while larger lists are closer to parity. The branch therefore favors exact bytes, not every accepted input representation.

Reproduce with `--commit ef925f5 --output docs/compressed-values-bytes-integrated-results.json`. [Integrated raw samples and source hashes](compressed-values-bytes-integrated-results.json) preserve this run separately.
