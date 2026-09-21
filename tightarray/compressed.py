"""Experimental adaptive uint8 storage with a byte-bounded packed write-back cache.

The cache limit covers packed data and palettes, not Python metadata or temporary
codec buffers. This is an in-memory container, not a persistence format. Instances
must not be accessed concurrently without an external lock.
"""

from __future__ import annotations

import importlib
import operator
import sys
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from itertools import islice
from typing import Literal, Protocol, SupportsIndex, cast, overload

from . import Array

__all__ = ["CompressedArray", "StorageInfo"]

_Bits = Literal[1, 2, 3, 4, 5, 6, 7, 8]
_CodecName = Literal["none", "lz4", "zstd"]
_Mode = Literal["packed", "bytes"]

# Buffer support predates the typing.Buffer protocol (Python 3.12). The runtime
# constructor validates it; incompatible formats retain elementwise validation.
_memoryview = cast(Callable[[object], memoryview], memoryview)


def _byte_view(values: object) -> memoryview | None:
    try:
        view = _memoryview(values)
    except TypeError:
        return None
    if view.ndim == 1 and view.format == "B" and view.c_contiguous:
        return view
    return None


class _Codecs(Protocol):
    LZ4: object
    ZSTD: object


class _Filters(Protocol):
    NOFILTER: object
    BITSHUFFLE: object


class _Native(Protocol):
    def _byte_palette(self, raw: bytes, /) -> bytes: ...
    def _byte_period(self, raw: bytes, /) -> int: ...
    def _rle_encode(
        self, raw: bytes, limit: int, palette: bytes = b""
    ) -> bytes | None: ...
    def _rle_decode(self, payload: bytes, length: int) -> bytes: ...

    def _Hot(
        self,
        data: Array,
        palette: bytes = b"",
        dirty: bool = False,
        *,
        length: int = ...,
    ) -> _Hot: ...


_native = cast(_Native, importlib.import_module("tightarray._core"))


class _Blosc(Protocol):
    Codec: _Codecs
    Filter: _Filters

    def compress2(
        self,
        src: bytes,
        *,
        codec: object,
        clevel: int,
        typesize: int,
        nthreads: int,
        filters: list[object],
    ) -> object: ...

    def decompress2(self, src: bytes, *, nthreads: int) -> object: ...


@dataclass(frozen=True, slots=True)
class StorageInfo:
    """Storage at this instant; flush first to inspect the latest cold encoding.

    stored_bytes includes palettes and the cold copies of cached chunks.
    owned_bytes additionally counts reachable container metadata and hot storage
    once, estimated using sys.getsizeof; it is not RSS, allocator capacity, or codec scratch.
    Uniform chunks have no payload but still have metadata.
    """

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
    periodic_chunks: int
    cache_hits: int
    cache_misses: int
    evictions: int


@dataclass(frozen=True, slots=True)
class _Chunk:
    length: int
    mode: _Mode
    bits: _Bits
    palette: bytes = b""
    payload: bytes = b""
    compressed: bool = False

    @property
    def nbytes(self) -> int:
        return len(self.palette) + len(self.payload)

    def seal(self) -> bytes:
        # Two private descriptor bytes, then palette and payload. Uniform chunks
        # remain scalar ints. Avoid retaining a Python record per nonuniform chunk.
        flags = (
            self.bits
            | (16 if self.compressed else 0)
            | (32 if self.mode == "bytes" else 0)
        )
        return bytes((flags, len(self.palette))) + self.palette + self.payload


class _Hot(Protocol):
    @property
    def data(self) -> Array: ...
    @property
    def palette(self) -> bytes: ...

    dirty: bool

    @property
    def repeated(self) -> bool: ...

    @property
    def nbytes(self) -> int: ...
    def read(self, start: int = 0, stop: int | None = None) -> bytes: ...
    def __getitem__(self, key: SupportsIndex, /) -> int: ...


_make_entry = _native._Hot


def _bits(maximum: int) -> _Bits:
    return cast(_Bits, max(1, maximum.bit_length()))


def _value(value: SupportsIndex) -> int:
    result = operator.index(value)
    if not 0 <= result <= 255:
        raise ValueError("value must fit logical uint8 (0..255)")
    return result


def _values(values: Iterable[SupportsIndex]) -> bytes:
    # bytes(int) means allocation, and bytes(buffer) can bypass element checks.
    view = _byte_view(values)
    return view.tobytes() if view is not None else bytes(iter(values))


def _raw(data: Array) -> bytes:
    view, start = data._word_view()
    assert start == 0  # Only freshly owned arrays; slices export their root buffer.
    return view.tobytes()


def _restore(payload: bytes, length: int, bits: _Bits) -> Array:
    # _from_word_bytes is a different, word-aligned big-endian wire format.
    return Array._from_packed_bytes(payload, length, bits)


class CompressedArray:
    """Fixed-length logical uint8 array with adaptive per-chunk compression.

    Cold chunks choose uniform, bit/palette packing, runs, or short periodic patterns.
    Optional Blosc2 LZ4/ZSTD also tries compressed packed and uint8 bytes. Only a
    smaller candidate is retained. Physical widths adapt silently; values outside
    uint8 always fail. Slices/read return independent bytes, never mutable views.

    cache_bytes=0 is write-through. Otherwise dirty packed chunks are written back
    on eviction/flush. Cold copies are retained while cached. All input validation
    in write() precedes mutation, but a codec/allocation error can leave an earlier
    chunk of a multi-chunk write committed. flush() does not release the cache.
    """

    def __init__(
        self,
        values: Iterable[SupportsIndex],
        *,
        chunk_size: SupportsIndex = 4096,
        cache_bytes: SupportsIndex = 262144,
        codec: _CodecName = "none",
        palette: bool = True,
    ) -> None:
        self._configure(chunk_size, cache_bytes, codec, palette)
        view = _byte_view(values)
        if view is not None:
            for start in range(0, len(view), self._chunk_size):
                self._append(view[start : start + self._chunk_size].tobytes())
        else:
            source = iter(values)
            while raw := bytes(islice(source, self._chunk_size)):
                self._append(raw)

    def _configure(
        self,
        chunk_size: SupportsIndex,
        cache_bytes: SupportsIndex,
        codec: _CodecName,
        palette: bool,
    ) -> None:
        self._chunk_size = operator.index(chunk_size)
        self._cache_limit = operator.index(cache_bytes)
        if self._chunk_size < 1 or self._cache_limit < 0:
            raise ValueError("chunk_size must be positive and cache_bytes nonnegative")
        if codec not in ("none", "lz4", "zstd"):
            raise ValueError("codec must be 'none', 'lz4', or 'zstd'")
        self._codec = codec
        self._palette = palette
        self._blosc: _Blosc | None = None
        if codec != "none":
            try:
                self._blosc = cast(_Blosc, importlib.import_module("blosc2"))
            except ImportError as exc:
                raise ImportError(
                    "LZ4/ZSTD require pip install 'tightarray[compression]'"
                ) from exc
        # Uniform chunks store their scalar directly: no per-chunk record/payload.
        self._chunks: list[bytes | int] = []
        self._cache: OrderedDict[int, _Hot] = OrderedDict()
        self._cache_used = 0
        self._length = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    @classmethod
    def full(
        cls,
        length: SupportsIndex,
        value: SupportsIndex = 0,
        *,
        chunk_size: SupportsIndex = 4096,
        cache_bytes: SupportsIndex = 262144,
        codec: _CodecName = "none",
        palette: bool = True,
    ) -> CompressedArray:
        """Construct uniform chunks without allocating a dense input array."""
        size, scalar = operator.index(length), _value(value)
        if size < 0:
            raise ValueError("length must be nonnegative")
        result = cls(
            (),
            chunk_size=chunk_size,
            cache_bytes=cache_bytes,
            codec=codec,
            palette=palette,
        )
        result._chunks = [scalar] * (
            (size + result._chunk_size - 1) // result._chunk_size
        )
        result._length = size
        return result

    def _append(self, raw: bytes) -> None:
        self._chunks.append(self._encode(raw))
        self._length += len(raw)

    def _compress(self, raw: bytes, *, shuffle: bool) -> bytes:
        api = self._blosc
        assert api is not None
        result = api.compress2(
            raw,
            codec=api.Codec.LZ4 if self._codec == "lz4" else api.Codec.ZSTD,
            typesize=1,
            clevel=5,
            nthreads=1,
            filters=[api.Filter.BITSHUFFLE if shuffle else api.Filter.NOFILTER],
        )
        if not isinstance(result, bytes):
            raise TypeError("Blosc2 did not return compressed bytes")
        return result

    def _decompress(self, raw: bytes) -> bytes:
        api = self._blosc
        assert api is not None
        result = api.decompress2(raw, nthreads=1)
        if not isinstance(result, bytes):
            raise TypeError("Blosc2 did not return decompressed bytes")
        return result

    def _encode(self, raw: bytes) -> bytes | int:
        colors = _native._byte_palette(raw)
        if len(colors) == 1:
            return raw[0]
        direct_bits = _bits(colors[-1])
        direct_size = ((len(raw) * direct_bits + 63) // 64) * 8
        palette_bits = _bits(len(colors) - 1)
        palette_size = ((len(raw) * palette_bits + 63) // 64) * 8 + len(colors)
        run_palette = colors if self._palette and palette_bits < direct_bits else b""
        best_size = min(direct_size, len(raw))
        if run_palette:
            best_size = min(best_size, palette_size)
        period_record = None
        period_bits = palette_bits if run_palette else direct_bits
        # Even the shortest packed pattern needs one word and a period byte.
        if best_size > 9 + len(run_palette):
            period = _native._byte_period(raw)
            if period:
                period_size = (
                    ((period * period_bits + 63) // 64) * 8 + 1 + len(run_palette)
                )
                if period_size < best_size:
                    pattern = raw[:period]
                    if run_palette:
                        translation = bytearray(256)
                        for index, color in enumerate(run_palette):
                            translation[color] = index
                        pattern = pattern.translate(bytes(translation))
                    payload = _raw(Array(pattern, bits=period_bits))
                    period_record = (
                        bytes((128 | period_bits, len(run_palette)))
                        + run_palette
                        + bytes((period - 1,))
                        + payload
                    )
                    best_size = period_size
        # Stop scanning as soon as runs cannot beat the best uncompressed form.
        # Retain the decode palette so cache misses never need to rediscover it.
        run_payload = _native._rle_encode(
            raw, best_size - len(run_palette), run_palette
        )
        run_record = None
        if run_payload is not None:
            run_bits = palette_bits if run_palette else direct_bits
            run_record = (
                bytes((64 | run_bits, len(run_palette))) + run_palette + run_payload
            )
        structured = run_record if run_record is not None else period_record
        if self._blosc is None:
            if structured is not None:
                return structured
            # Packed lengths are known before allocation. Preserve the exhaustive
            # candidate ordering on ties without constructing discarded arrays.
            mode: _Mode = "packed" if direct_size <= len(raw) else "bytes"
            best_size = min(direct_size, len(raw))
            if (
                self._palette
                and palette_bits < direct_bits
                and palette_size < best_size
            ):
                translation = bytearray(256)
                for index, color in enumerate(colors):
                    translation[color] = index
                indices = Array(raw.translate(bytes(translation)), bits=palette_bits)
                return _Chunk(
                    len(raw), "packed", palette_bits, colors, _raw(indices)
                ).seal()
            payload = _raw(Array(raw, bits=direct_bits)) if mode == "packed" else raw
            return _Chunk(len(raw), mode, direct_bits, payload=payload).seal()
        direct = Array(raw, bits=direct_bits, layout="packed")
        candidates = [
            _Chunk(len(raw), "packed", cast(_Bits, direct.bits), payload=_raw(direct)),
            _Chunk(len(raw), "bytes", cast(_Bits, direct.bits), payload=raw),
        ]
        if self._palette and len(colors) < 256:
            palette_bits = _bits(len(colors) - 1)
            # A palette can save bits only when its index width is narrower.
            if palette_bits < direct.bits:
                translation = bytearray(256)
                for index, color in enumerate(colors):
                    translation[color] = index
                indices = Array(raw.translate(bytes(translation)), bits=palette_bits)
                candidates.append(
                    _Chunk(len(raw), "packed", palette_bits, colors, _raw(indices))
                )
        if self._blosc is not None:
            for candidate in tuple(candidates):
                if len(candidate.payload) < 64:
                    continue
                payload = self._compress(
                    candidate.payload, shuffle=candidate.mode == "bytes"
                )
                if len(payload) < len(candidate.payload):
                    candidates.append(
                        _Chunk(
                            candidate.length,
                            candidate.mode,
                            candidate.bits,
                            candidate.palette,
                            payload,
                            True,
                        )
                    )
        winner = min(candidates, key=lambda candidate: candidate.nbytes)
        if structured is not None and len(structured) - 2 < winner.nbytes:
            return structured
        return winner.seal()

    def _chunk_length(self, index: int) -> int:
        return min(self._chunk_size, self._length - index * self._chunk_size)

    def _decode(self, chunk: bytes | int, length: int) -> _Hot:
        if isinstance(chunk, int):
            return _make_entry(Array(bytes(length), bits=1), bytes([chunk]))
        flags, count = chunk[0], chunk[1]
        bits = cast(_Bits, flags & 15)
        palette = chunk[2 : 2 + count]
        if flags & 128:
            period = chunk[2 + count] + 1
            pattern = Array._from_packed_bytes(chunk, period, bits, 3 + count)
            return _make_entry(pattern, palette, length=length)
        if flags & 64:
            raw = _native._rle_decode(chunk[2 + count :], length)
            return _make_entry(Array(raw, bits=bits), palette)
        if not flags & 48:  # Uncompressed packed storage: copy straight to words.
            return _make_entry(
                Array._from_packed_bytes(chunk, length, bits, 2 + count), palette
            )
        payload = chunk[2 + count :]
        raw = self._decompress(payload) if flags & 16 else payload
        if flags & 32:
            if len(raw) != length:
                raise ValueError("invalid internal uint8 payload length")
            return _make_entry(Array(raw, bits=bits))
        return _make_entry(_restore(raw, length, bits), palette)

    def _make_hot(self, raw: bytes) -> _Hot:
        """Choose a compact mutable representation independently of cold codecs."""
        colors = _native._byte_palette(raw) if self._palette else b""
        direct_bits = _bits(colors[-1] if colors else max(raw, default=0))
        if colors:
            palette_bits = _bits(len(colors) - 1)
            direct_size = ((len(raw) * direct_bits + 63) // 64) * 8
            palette_size = ((len(raw) * palette_bits + 63) // 64) * 8 + len(colors)
            if palette_size < direct_size:
                translation = bytearray(256)
                for index, color in enumerate(colors):
                    translation[color] = index
                return _make_entry(
                    Array(raw.translate(bytes(translation)), bits=palette_bits), colors
                )
        return _make_entry(Array(raw, bits=direct_bits))

    def _writeback(self, index: int, hot: _Hot) -> None:
        if hot.dirty:
            replacement = self._encode(hot.read())
            self._chunks[index] = replacement
            hot.dirty = False

    def _reserve(self, needed: int, replacing: int | None = None) -> None:
        old = self._cache.get(replacing) if replacing is not None else None
        old_size = old.nbytes if old is not None else 0
        while self._cache_used - old_size + needed > self._cache_limit:
            victim = next(index for index in self._cache if index != replacing)
            hot = self._cache[victim]
            # Keep the authoritative dirty entry if encoding fails.
            self._writeback(victim, hot)
            del self._cache[victim]
            self._cache_used -= hot.nbytes
            self._evictions += 1

    def _get_hot(self, index: int) -> _Hot:
        hot = self._cache.get(index)
        if hot is not None:
            self._hits += 1
            self._cache.move_to_end(index)
            return hot
        self._misses += 1
        hot = self._decode(self._chunks[index], self._chunk_length(index))
        if hot.nbytes <= self._cache_limit:
            self._reserve(hot.nbytes)
            self._cache[index] = hot
            self._cache_used += hot.nbytes
        return hot

    def _commit_hot(self, index: int, hot: _Hot) -> None:
        old = self._cache.get(index)
        old_size = old.nbytes if old is not None else 0
        hot.dirty = True
        if hot.nbytes > self._cache_limit:
            # Encode fully before swapping cold storage or removing the old cache.
            replacement = self._encode(hot.read())
            self._chunks[index] = replacement
            if old is not None:
                del self._cache[index]
                self._cache_used -= old_size
            return
        self._reserve(hot.nbytes, replacing=index)
        self._cache[index] = hot
        self._cache.move_to_end(index)
        self._cache_used += hot.nbytes - old_size

    def __len__(self) -> int:
        return self._length

    def __iter__(self) -> Iterator[int]:
        for start in range(0, self._length, self._chunk_size):
            yield from self.read(start, min(self._length, start + self._chunk_size))

    def _index(self, key: SupportsIndex) -> tuple[int, int]:
        index = operator.index(key)
        if index < 0:
            index += self._length
        if not 0 <= index < self._length:
            raise IndexError("CompressedArray index out of range")
        return divmod(index, self._chunk_size)

    @overload
    def __getitem__(self, key: SupportsIndex, /) -> int: ...

    @overload
    def __getitem__(self, key: slice, /) -> bytes: ...

    def __getitem__(self, key: SupportsIndex | slice, /) -> int | bytes:
        if isinstance(key, slice):
            start, stop, step = key.indices(self._length)
            if step == 1:
                return self.read(start, max(start, stop))
            return bytes(self[index] for index in range(start, stop, step))
        position = operator.index(key)
        if position < 0:
            position += self._length
        if not 0 <= position < self._length:
            raise IndexError("CompressedArray index out of range")
        index, offset = divmod(position, self._chunk_size)
        # The hot scalar path avoids two Python calls and cold metadata access.
        hot = self._cache.get(index)
        if hot is None:
            chunk = self._chunks[index]
            if isinstance(chunk, int):
                return chunk
            hot = self._get_hot(index)
        else:
            self._hits += 1
            self._cache.move_to_end(index)
        return hot[offset]

    def __setitem__(self, key: SupportsIndex, value: SupportsIndex, /) -> None:
        index, offset = self._index(key)
        scalar = _value(value)
        chunk = self._chunks[index]
        if isinstance(chunk, int) and index not in self._cache and chunk == scalar:
            return
        hot = self._get_hot(index)
        encoded = hot.palette.find(bytes([scalar])) if hot.palette else scalar
        if (
            not hot.repeated
            and 0 <= encoded < 1 << hot.data.bits
            and self._cache.get(index) is hot
        ):
            hot.data[offset] = encoded
            hot.dirty = True
            return
        # Width/palette changes use a new entry, preserving old data on failure.
        raw = bytearray(hot.read())
        raw[offset] = scalar
        self._commit_hot(index, self._make_hot(bytes(raw)))

    def _range(
        self, start: SupportsIndex, stop: SupportsIndex | None
    ) -> tuple[int, int]:
        first = operator.index(start)
        last = self._length if stop is None else operator.index(stop)
        if not 0 <= first <= last <= self._length:
            raise IndexError("range must satisfy 0 <= start <= stop <= len(array)")
        return first, last

    def read(
        self, start: SupportsIndex = 0, stop: SupportsIndex | None = None
    ) -> bytes:
        """Read a validated half-open range as independent uint8 bytes."""
        first, last = self._range(start, stop)
        parts: list[bytes] = []
        while first < last:
            index, offset = divmod(first, self._chunk_size)
            chunk = self._chunks[index]
            count = min(self._chunk_length(index) - offset, last - first)
            if isinstance(chunk, int) and index not in self._cache:
                parts.append(bytes([chunk]) * count)
            else:
                parts.append(self._get_hot(index).read(offset, offset + count))
            first += count
        return b"".join(parts)

    def write(self, start: SupportsIndex, values: Iterable[SupportsIndex]) -> None:
        """Validate all values/bounds before mutation; codec failures may be partial."""
        first = operator.index(start)
        raw = _values(values)
        self._range(first, first + len(raw))
        consumed = 0
        while consumed < len(raw):
            index, offset = divmod(first, self._chunk_size)
            length = self._chunk_length(index)
            count = min(length - offset, len(raw) - consumed)
            if offset == 0 and count == length:
                replacement = raw[consumed : consumed + count]
            else:
                data = bytearray(self._get_hot(index).read())
                data[offset : offset + count] = raw[consumed : consumed + count]
                replacement = bytes(data)
            self._commit_hot(index, self._make_hot(replacement))
            first += count
            consumed += count

    def tobytes(self) -> bytes:
        return self.read()

    def flush(self) -> None:
        """Encode dirty chunks, retaining cache entries; failure preserves updates."""
        for index, hot in self._cache.items():
            self._writeback(index, hot)

    def clear_cache(self) -> None:
        """Flush then release the cache. A failed flush leaves the cache intact."""
        self.flush()
        self._cache.clear()
        self._cache_used = 0

    def storage_info(self) -> StorageInfo:
        seen: set[int] = set()

        def size(obj: object) -> int:
            if id(obj) in seen:
                return 0
            seen.add(id(obj))
            return sys.getsizeof(obj)

        owned = (
            size(self) + size(self.__dict__) + size(self._chunks) + size(self._cache)
        )
        owned += sum(size(chunk) for chunk in self._chunks)
        owned += sum(
            size(index) + size(hot) + size(hot.data) + size(hot.palette)
            for index, hot in self._cache.items()
        )
        # Codec module/class internals are shared runtime state, not owned storage.
        owned += sum(
            size(value)
            for key, value in self.__dict__.items()
            if key not in ("_blosc", "_chunks", "_cache")
        )
        return StorageInfo(
            self._length,
            sum(len(chunk) - 2 for chunk in self._chunks if isinstance(chunk, bytes)),
            self._cache_used,
            self._cache_limit,
            owned,
            len(self._chunks),
            sum(isinstance(chunk, int) for chunk in self._chunks),
            sum(bool(chunk[1]) for chunk in self._chunks if isinstance(chunk, bytes)),
            sum(
                bool(chunk[0] & 16)
                for chunk in self._chunks
                if isinstance(chunk, bytes)
            ),
            sum(
                bool(chunk[0] & 64)
                for chunk in self._chunks
                if isinstance(chunk, bytes)
            ),
            sum(
                bool(chunk[0] & 128)
                for chunk in self._chunks
                if isinstance(chunk, bytes)
            ),
            self._hits,
            self._misses,
            self._evictions,
        )
