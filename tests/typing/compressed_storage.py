from typing import assert_type

from tightarray.compressed import CompressedArray, StorageInfo

array = CompressedArray([1, 2, 255], chunk_size=1024, codec="none")
assert_type(array[0], int)
assert_type(array[1:], bytes)
assert_type(array.read(), bytes)
assert_type(array.storage_info(), StorageInfo)
assert_type(array.storage_info().cache_bytes, int)
assert_type(CompressedArray.full(1000, 255), CompressedArray)
array[0] = 255
array.write(0, (v for v in range(3)))
array.flush()
array.clear_cache()

array[0] = "bad"  # type: ignore[assignment]
CompressedArray([0], codec="invalid")  # type: ignore[arg-type]
array.storage_info().stored_bytes = 0  # type: ignore[misc]
