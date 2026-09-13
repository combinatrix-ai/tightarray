# Benchmark plan

## Comparison groups

| Implementation | Baseline |
| --- | --- |
| Standard Python | list[int], nested lists; bytes and str for corresponding sequence operations |
| NumPy | uint8 arrays; rectangular arrays; flat uint8 data plus native offsets for ragged arrays |
| tightarray | Packed and word-aligned layouts reported separately |

Use identical logical values and shapes. NumPy uint8 is the smallest ordinary unsigned integer dtype covering the initial range. Small Python integers may be shared; do not assume one distinct integer object per element.

## Methods

Measure construction, scalar get/set, contiguous slices, batch gather, iteration, equality, count, and subsequence search. Include matrix element/row access and ragged element/row access when implemented.

Compare equivalent semantics. View creation and copying are distinct benchmarks. Report unsupported baseline operations as N/A rather than substituting an unrelated operation. Conversion and construction costs are separate measurements, with end-to-end cases where useful.

## Metrics

For each method, report:

- Retained memory of the resulting representation, including ownership metadata and offsets.
- Additional peak memory during the operation, separately from retained memory.
- Time per operation; time per element or throughput for bulk operations.

Count shared Python allocations once. Include native extension and NumPy buffers; Python allocation tracing alone is insufficient. Separate allocator/process overhead from representation size. Use isolated processes for peak measurements where appropriate, and label measurement limitations.

Suggested result columns: method, structure, bit width, shape/length, implementation, layout, retained bytes, additional peak bytes, time/op, time/element, variability.

## Workloads and measurement discipline

- Initial widths: 2, 5, 7; later cover 1–8.
- Sweep data sizes from small arrays through cache-resident and memory-bound workloads.
- Include sequential and random access with indices generated outside the timed region.
- Cover uniform and skewed values, equal/unequal sequences, and ragged row-length distributions.
- Separate Python-call overhead from bulk operations performed within C.
- Use deterministic seeds, warmups, repeated samples, and record software/compiler/CPU details with results.
- Compare scalar references and optimized kernels; verify outputs before timing.
- Include empty arrays, boundary indices, cross-word elements, tail padding, empty rows, and invalid values in correctness checks.
- Define slice ownership, overflow rejection, and mutation semantics before implementing affected benchmarks.

No speedup or memory result has been measured yet. The benchmark runner and exact measurement tooling remain to be implemented.
