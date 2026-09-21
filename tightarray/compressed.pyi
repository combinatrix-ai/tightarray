from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal, SupportsIndex, TypeAlias, overload

_Codec: TypeAlias = Literal["none", "lz4", "zstd"]

@dataclass(frozen=True, slots=True)
class StorageInfo:
    logical_bytes: int
    stored_bytes: int
    cache_bytes: int
    cache_limit_bytes: int
    owned_bytes: int
    chunk_count: int
    uniform_chunks: int
    palette_chunks: int
    compressed_chunks: int
    rle_chunks: int
    cache_hits: int
    cache_misses: int
    evictions: int

class CompressedArray:
    def __init__(
        self,
        values: Iterable[SupportsIndex],
        *,
        chunk_size: SupportsIndex = ...,
        cache_bytes: SupportsIndex = ...,
        codec: _Codec = ...,
        palette: bool = ...,
    ) -> None: ...
    @classmethod
    def full(
        cls,
        length: SupportsIndex,
        value: SupportsIndex = ...,
        *,
        chunk_size: SupportsIndex = ...,
        cache_bytes: SupportsIndex = ...,
        codec: _Codec = ...,
        palette: bool = ...,
    ) -> CompressedArray: ...
    def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[int]: ...
    @overload
    def __getitem__(self, key: SupportsIndex, /) -> int: ...
    @overload
    def __getitem__(self, key: slice, /) -> bytes: ...
    def __setitem__(self, key: SupportsIndex, value: SupportsIndex, /) -> None: ...
    def read(
        self, start: SupportsIndex = ..., stop: SupportsIndex | None = ...
    ) -> bytes: ...
    def write(self, start: SupportsIndex, values: Iterable[SupportsIndex]) -> None: ...
    def tobytes(self) -> bytes: ...
    def flush(self) -> None: ...
    def clear_cache(self) -> None: ...
    def storage_info(self) -> StorageInfo: ...
