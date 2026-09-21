# Input dispatch policy comparison

Benchmark-only isolated modules compare pinned `ef925f5` (original helper), `6ea92e7` (exact-bytes helper), and three injected alternatives based on `ef925f5`. The alternatives move the bytes branch into `write`, additionally shortcut exact list/tuple through `bytes(iter(values))`, or instead use `bytes(values)` for those exact built-in containers. Subclasses retain the original fallback; scalar integers, bad elements, mutable snapshots, signed/wide buffers, and generator validation are not weakened. Ten tests exercise these contracts without Git history.

All policies share the same native extension. Every matrix cell has eleven shuffled paired repeats. Helper calls use 5,000 operations per repeat; complete-write measurements use 128 alternating writes into a warm 8,192-byte ordinary chunk followed by one flush. Every write changes all addressed values. Tested widths are 1, 16, 64, 256, and 4,096 bytes, always partial chunks; input kinds are bytes, bytearray, memoryview, list, tuple, and generator. Fresh generator creation occurs inside each timed call, consistently across policies. Other inputs are prepared before timing. No codec is used. This is a focused synthetic test, not application throughput.

## Complete-write medians

Nanoseconds per write, with flush amortized over 128 writes:

| Input | Width | Original | Helper bytes | Write bytes | Write containers via iterator | Write containers direct |
|---|---:|---:|---:|---:|---:|---:|
| bytes | 1 | 909.2 | 731.1 | 711.6 | 714.2 | 714.2 |
| bytearray | 1 | 878.2 | 901.0 | 910.8 | 907.9 | 919.9 |
| memoryview | 1 | 872.7 | 889.6 | 867.8 | 879.9 | 898.4 |
| list | 1 | 1053.7 | 1072.6 | 1083.7 | 812.5 | 746.1 |
| tuple | 1 | 1065.1 | 1079.4 | 1072.6 | 820.3 | 759.4 |
| generator | 1 | 1183.6 | 1202.1 | 1192.7 | 1212.2 | 1221.0 |
| bytes | 16 | 911.1 | 749.3 | 736.0 | 742.8 | 733.7 |
| bytearray | 16 | 898.8 | 909.2 | 911.8 | 923.2 | 932.0 |
| memoryview | 16 | 875.7 | 883.5 | 898.1 | 901.4 | 902.0 |
| list | 16 | 1154.0 | 1168.9 | 1181.3 | 902.0 | 834.3 |
| tuple | 16 | 1168.3 | 1190.1 | 1183.9 | 906.2 | 817.4 |
| generator | 16 | 1514.6 | 1526.7 | 1523.8 | 1548.8 | 1549.8 |
| bytes | 64 | 1031.6 | 871.4 | 853.5 | 870.1 | 857.4 |
| bytearray | 64 | 1050.1 | 1042.6 | 1054.7 | 1062.5 | 1079.8 |
| memoryview | 64 | 1022.5 | 1020.5 | 1018.2 | 1028.3 | 1054.7 |
| list | 64 | 1431.6 | 1445.6 | 1448.2 | 1184.9 | 1071.0 |
| tuple | 64 | 1427.7 | 1445.3 | 1438.5 | 1178.4 | 1035.2 |
| generator | 64 | 2550.8 | 2546.2 | 2613.6 | 2575.8 | 2572.6 |
| bytes | 256 | 1518.2 | 1343.1 | 1284.8 | 1326.5 | 1303.4 |
| bytearray | 256 | 1456.1 | 1457.4 | 1460.0 | 1481.8 | 1488.6 |
| memoryview | 256 | 1433.3 | 1449.9 | 1461.6 | 1463.2 | 1464.8 |
| list | 256 | 2451.8 | 2467.8 | 2485.0 | 2229.8 | 1940.4 |
| tuple | 256 | 2476.2 | 2496.1 | 2538.7 | 2264.6 | 1862.3 |
| generator | 256 | 6703.8 | 6576.2 | 6593.4 | 6661.8 | 6687.2 |
| bytes | 4096 | 10574.2 | 9690.8 | 9768.2 | 9456.1 | 9750.0 |
| bytearray | 4096 | 9418.0 | 9636.7 | 10006.8 | 9581.1 | 9634.4 |
| memoryview | 4096 | 9830.1 | 9659.5 | 9573.6 | 9578.5 | 9585.9 |
| list | 4096 | 23264.0 | 22661.5 | 23307.9 | 22865.9 | 19765.0 |
| tuple | 4096 | 22766.9 | 23102.9 | 22751.0 | 22606.8 | 17478.2 |
| generator | 4096 | 90571.3 | 89857.1 | 90352.9 | 90972.3 | 89627.9 |

Moving the bytes check alone does not solve list overhead: list writes still range from 0.2% to 2.9% slower than the original. Its bytes gains are slightly larger at some small widths, but the helper change was not the only possible source of dispatch overhead.

The exact list/tuple direct `bytes(values)` shortcut improves list writes 15–29% and tuple writes 23–30% versus the original. It outperforms `bytes(iter(values))` for every tested list/tuple width. This avoids the original failed buffer probe and takes the built-in container conversion path. It remains valid only behind exact-type checks: subclasses may override iteration or supply other semantics.

The tradeoff remains explicit. Direct-container dispatch costs bytearray roughly 2.2–4.7%, memoryview up to 3.1% at small widths (the 4,096-byte row improves 2.5%), and short generators up to 3.2%. It therefore favors bytes/list/tuple, not every accepted input representation. `_values` is used only by `write`; moving this branch does not change constructor ingestion. The earlier version of this paragraph incorrectly inferred a constructor effect.

## Repeat consistency

Ratio of direct-container write median to original median, computed separately from the first five and last six samples for each policy (less than one is faster):

| Input | Width | First five | Last six |
|---|---:|---:|---:|
| list | 1 | 0.735 | 0.703 |
| tuple | 1 | 0.754 | 0.716 |
| list | 16 | 0.702 | 0.721 |
| tuple | 16 | 0.701 | 0.707 |
| list | 64 | 0.736 | 0.749 |
| tuple | 64 | 0.729 | 0.723 |
| list | 256 | 0.788 | 0.793 |
| tuple | 256 | 0.748 | 0.771 |
| list | 4096 | 0.850 | 0.848 |
| tuple | 4096 | 0.804 | 0.763 |

Both halves preserve the list/tuple benefit at every tested width. The earlier single 7.1% short-list regression was not reproduced at that magnitude in this alternating-write workload; that is a workload-dependent observation, not evidence to dismiss it as noise. Raw samples remain available for comparison.

All 60 cells × five policies × eleven repeats passed equality and source guards. [Raw samples and provenance](compressed-input-dispatch-results.json) include helper controls, which intentionally measure `_values` itself: write-site variants share the unchanged original helper, so their helper results provide repeatability controls rather than measuring write-site dispatch.

Run `python -m benchmarks.compressed_input_dispatch --output docs/compressed-input-dispatch-results.json`. No production source was edited during this experiment.

After the original measurement, the harness gained a typed direct-container candidate differing only by `cast(bytes, values)` in the exact-bytes branch, plus `--cast-only` to omit helper microbenchmarks. Tests normalize the adopted typed write block before constructing the variants. The historical JSON and its recorded harness hash remain untouched; this maintenance changes the current script hash.

## Typed adopted policy versus earlier policies

The second, write-only experiment includes the original `ef925f5`, helper-fastpath `6ea92e7`, untyped direct-container policy, and adopted typed policy in the same eleven-repeat randomized comparison. The typed policy differs from the untyped one only by `cast(bytes, values)` on exact bytes. It uses the current frozen native extension, including the byte-aligned assignment optimization. There is no cross-run ratio chaining.

Median nanoseconds per write, with one flush after 128 alternating changes:

| Input | Width | Original | Prior helper | Direct untyped | Direct typed |
|---|---:|---:|---:|---:|---:|
| bytes | 1 | 870.8 | 711.3 | 699.2 | 718.4 |
| bytearray | 1 | 871.1 | 877.3 | 889.6 | 890.6 |
| memoryview | 1 | 844.7 | 856.4 | 868.2 | 863.0 |
| list | 1 | 1052.7 | 1067.7 | 751.0 | 744.5 |
| tuple | 1 | 1056.3 | 1072.6 | 757.8 | 762.0 |
| generator | 1 | 1186.5 | 1190.1 | 1204.8 | 1206.4 |
| bytes | 16 | 897.8 | 745.4 | 750.6 | 759.8 |
| bytearray | 16 | 881.8 | 895.2 | 907.2 | 909.8 |
| memoryview | 16 | 861.6 | 877.0 | 887.7 | 887.4 |
| list | 16 | 1131.8 | 1148.8 | 803.7 | 803.1 |
| tuple | 16 | 1129.2 | 1149.4 | 804.4 | 808.6 |
| generator | 16 | 1500.3 | 1518.9 | 1538.4 | 1533.9 |
| bytes | 64 | 1011.7 | 863.9 | 846.4 | 873.0 |
| bytearray | 64 | 1013.7 | 1027.7 | 1035.5 | 1038.4 |
| memoryview | 64 | 1013.0 | 1019.9 | 1035.2 | 1029.6 |
| list | 64 | 1442.1 | 1439.1 | 1069.7 | 1068.4 |
| tuple | 64 | 1412.8 | 1417.3 | 1029.6 | 1032.6 |
| generator | 64 | 2527.3 | 2542.3 | 2547.9 | 2554.7 |
| bytes | 256 | 1490.6 | 1329.8 | 1291.0 | 1331.7 |
| bytearray | 256 | 1439.5 | 1453.8 | 1454.8 | 1454.4 |
| memoryview | 256 | 1434.2 | 1422.9 | 1446.6 | 1444.3 |
| list | 256 | 2434.2 | 2440.8 | 1922.5 | 1926.8 |
| tuple | 256 | 2493.2 | 2436.5 | 1830.4 | 1830.7 |
| generator | 256 | 6627.0 | 6574.9 | 6620.4 | 6576.8 |
| bytes | 4096 | 9460.3 | 9318.0 | 9307.3 | 9487.0 |
| bytearray | 4096 | 9526.0 | 9406.9 | 9481.4 | 9562.5 |
| memoryview | 4096 | 9375.3 | 9542.3 | 9613.9 | 9425.5 |
| list | 4096 | 22836.6 | 22687.2 | 19644.5 | 19653.3 |
| tuple | 4096 | 23115.2 | 22720.4 | 17329.4 | 17300.1 |
| generator | 4096 | 88878.3 | 88603.2 | 88635.4 | 89499.3 |

Compared directly with the prior helper-fastpath policy, typed dispatch improves lists 13.4–30.3% and tuples 23.9–29.7%. The same run shows bytes 0.15–1.92% slower, bytearray 0.05–1.65% slower, memoryview from 1.22% faster to 1.51% slower, and generators 0.03–1.37% slower. This is a deliberate list/tuple improvement with small measured costs elsewhere, not a universal speedup.

The typed versus untyped bytes difference is 1.2–3.2%; at widths up to 256 it is about 9–41 ns per write. The 4,096-byte row differs by about 180 ns against a roughly 9.4 µs operation, so that absolute delta cannot all be assigned confidently to the one cast call. Against the original pre-fastpath baseline, adopted bytes dispatch still improves widths up to 256 by 10.7–17.5%, while the 4,096-byte row is 0.28% slower. All source guards and exact-output checks pass across 30 cases × four policies × eleven repeats.

Reproduce with `python -m benchmarks.compressed_input_dispatch --cast-only --output docs/compressed-input-dispatch-typed-results.json`. [Typed-policy raw samples and provenance](compressed-input-dispatch-typed-results.json) are separate from the unchanged historical artifact. No further production changes are part of this experiment.
