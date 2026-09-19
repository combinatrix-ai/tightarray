from collections.abc import Callable
from typing import Literal, NamedTuple

import numpy as np

from . import Array

class NativeArray(NamedTuple):
    words: np.ndarray[tuple[int, ...], np.dtype[np.uint64]]
    start: int
    length: int
    bits: int
    aligned: bool

def as_native(array: Array) -> NativeArray: ...
def load(array: NativeArray, index: int) -> int: ...
def store(array: NativeArray, index: int, value: int) -> None: ...
def specialize(
    bits: int, layout: Literal["packed", "word-aligned"] = ...
) -> tuple[
    Callable[[NativeArray, int], int], Callable[[NativeArray, int, int], None]
]: ...
