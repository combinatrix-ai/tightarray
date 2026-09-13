# NumPy API measurements

Apple M1 Pro; Public NumPy calls include dispatch and any unpacking; np.asarray(ndarray) may share data, while tightarray always copies. Deterministic periodic input; no isolation or cold-cache control.

These timings include NumPy dispatch and unpacking, separately from direct native methods.

`count_nonzero(ndarray)` needs no equality-mask allocation, unlike the value-count baseline in the native benchmark.

Median microseconds per public NumPy call; lower is better.

## 65,536 elements, 2 bits

| NumPy call | ndarray | Packed | Word-aligned |
| --- | ---: | ---: | ---: |
| asarray | 0.053 | 8.961 | 8.930 |
| array_equal | 4.272 | 2.698 | 2.738 |
| count_nonzero | 2.464 | 2.561 | 2.576 |
| take | 1.144 | 2.373 | 2.393 |
| add | 1.572 | 15.620 | 15.298 |

## 65,536 elements, 5 bits

| NumPy call | ndarray | Packed | Word-aligned |
| --- | ---: | ---: | ---: |
| asarray | 0.053 | 12.802 | 11.822 |
| array_equal | 4.256 | 3.411 | 3.580 |
| count_nonzero | 2.420 | 5.038 | 3.672 |
| take | 1.147 | 2.472 | 2.408 |
| add | 1.423 | 19.465 | 19.422 |

## 65,536 elements, 7 bits

| NumPy call | ndarray | Packed | Word-aligned |
| --- | ---: | ---: | ---: |
| asarray | 0.053 | 15.962 | 14.417 |
| array_equal | 4.248 | 4.070 | 4.124 |
| count_nonzero | 2.468 | 5.187 | 4.246 |
| take | 1.130 | 2.465 | 2.432 |
| add | 1.644 | 22.871 | 21.329 |

## 1,048,576 elements, 2 bits

| NumPy call | ndarray | Packed | Word-aligned |
| --- | ---: | ---: | ---: |
| asarray | 0.053 | 121.519 | 119.237 |
| array_equal | 49.545 | 9.259 | 9.159 |
| count_nonzero | 36.121 | 12.724 | 12.759 |
| take | 1.148 | 2.334 | 2.374 |
| add | 22.833 | 146.390 | 144.589 |

## 1,048,576 elements, 5 bits

| NumPy call | ndarray | Packed | Word-aligned |
| --- | ---: | ---: | ---: |
| asarray | 0.052 | 179.711 | 164.987 |
| array_equal | 49.510 | 18.854 | 19.941 |
| count_nonzero | 36.097 | 53.946 | 30.160 |
| take | 1.141 | 2.528 | 2.373 |
| add | 22.928 | 207.891 | 190.232 |

## 1,048,576 elements, 7 bits

| NumPy call | ndarray | Packed | Word-aligned |
| --- | ---: | ---: | ---: |
| asarray | 0.052 | 370.960 | 201.815 |
| array_equal | 49.490 | 25.578 | 25.669 |
| count_nonzero | 36.123 | 53.952 | 39.466 |
| take | 1.144 | 2.492 | 2.477 |
| add | 22.743 | 254.609 | 229.810 |

## Interpretation

- Whole-array equality retains a packed-kernel advantage at these sizes.
- NumPy take dispatch costs more than direct `.gather()` and is slower than take on an existing ndarray here.
- Ufunc arithmetic unpacks first; it is interoperability, not an accelerated arithmetic kernel.
- `np.asarray(ndarray)` can share storage; tightarray always creates an independent writable array.
- Result retention and traced peak memory are recorded per method. Conversion peaks include intermediate bytes and a writable bytearray.

[Raw samples and source hashes](results/m1-pro-numpy-api.json) · [Timing and memory CSV](results/numpy-api.csv)
