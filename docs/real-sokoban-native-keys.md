# Fused packed keys in actual Sokoban search

This integration experiment calls the existing private C `_pack_bytes` helper directly instead of creating an Array, a word-buffer exporter and final bytes for every visited-state key. The key remains exactly the same word-padded3-bit bytes. There is no new production kernel, compression codec, or search algorithm. The input uint8 conversion remains included for both uint8 and packed alternatives.

Pinned gym-sokoban source `8e06e44e8bf3bb8bc73eeb1e7f0354508ce3fc89` (SHA enforced by the existing runner) executes its actual room generation/reverse search, seed37,10x10,four boxes. Each method/cap has five fresh processes, seeded shuffled method order. Startup/imports are excluded from search timing. All50 searches match visited counts,key calls,score,board digest and box mapping within their cap; native keys match the previous packed encoder exactly on separate shape/stride tests. The larger cap50000 naturally exhausts at25226 states.

CPython3.12.8, NumPy2.5.3, ARM64, current native kernel from9f72f0c. Complete core source/binary guards and experiment script hash are in the [raw artifact](real-sokoban-native-keys-results.json.gz); guards were checked before/after measurement. Medians are same-run comparisons, not historical speedup estimates.

| Cap / visited | Encoder | Search seconds | Retained keyset bytes |
|---|---|---:|---:|
|5000 /5000|Original marshal|0.205589|4714504|
|5000 /5000|uint8|0.200714|1189504|
|5000 /5000|Array-based packed|0.220743|889504|
|5000 /5000|Native packed|0.202401|889504|
|5000 /5000|Sparse|0.318843|764504|
|50000 /25226|Original marshal|1.031669|23236756|
|50000 /25226|uint8|1.004816|5452426|
|50000 /25226|Array-based packed|1.106739|3938866|
|50000 /25226|Native packed|1.017871|3938866|
|50000 /25226|Sparse|1.622475|3308216|

Native packed construction cuts whole-search time8.0–8.3% versus the existing Array-based adapter. Compared with uint8, it retains25.2–27.8% less keyset memory while taking0.8–1.3% more time in these medians. This is near parity at this exploratory precision, **not a demonstrated speed win over uint8**. The sparse key is smaller still but slower here. Original marshal's much larger footprint is not the strongest baseline.

Memory is `sys.getsizeof(set)+sum(sys.getsizeof(key))`, excluding active boards, recursion, shared data, allocator overhead and process RSS. One puzzle seed and two caps do not establish a general solver capacity frontier. Key correctness tests cover non-contiguous boards, small shapes and partial word tails; they do not establish a portable serialized format. The helper is private experimental API, so this remains an integration pilot rather than a supported upstream adapter.

```sh
python -m pytest tests/test_real_sokoban_native_keys.py tests/test_real_sokoban_search.py -q
python -m benchmarks.real_sokoban_native_keys --output /tmp/sokoban-native.json
```
