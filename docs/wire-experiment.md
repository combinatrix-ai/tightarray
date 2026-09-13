# Experimental packed wire codec

The Quarry integration uses two private Array methods for 64-bit big-endian words with least-significant-bit-first integer lanes. Widths are 1–8 bits; each word holds `64 // bits` values without crossing word boundaries. This is an experiment, not a stable serialization API.

`Array._from_word_bytes(data, length, bits)` copies packed bytes directly to native word-aligned storage and returns `(array, padding)`. The byte count must exactly match the logical length rounded up to full words. `padding` is `None` for canonical zero padding, otherwise bytes containing only unused high/tail bits. Keeping padding outside the array preserves normal reductions and equality.

`array._to_word_bytes(padding)` exports in that same format. It supports packed storage and sliced views too. Padding must be `None` or bytes of the matching length; bits in occupied lanes are ignored. It does not retain or alias the caller's buffer. Width, length and padding errors raise ValueError. Length conversion overflow follows normal CPython argument parsing.

The application retains any bytes after the logical word region and handles 8-bit sectors separately. No Minecraft-specific palette, NBT or registry rules are included in tightarray. These methods avoid intermediate NumPy arrays and per-element Python objects; export still allocates the result bytes.
