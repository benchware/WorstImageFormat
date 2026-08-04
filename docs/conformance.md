# WIM2 conformance vectors

`tests/conformance/vectors.json` is the first language-neutral decoder
conformance pack. Each WIM2 payload is Base64-wrapped only so it can be reviewed
and copied through text systems. The manifest records:

- container SHA-256;
- exact decoded-pixel SHA-256;
- dimensions, channels, and bit depth;
- the required recorded tile mode.

The pack contains lossless Raw, Predictive, Palette, and Wavelet vectors plus
grayscale, RGBA, 10-bit, 16-bit, odd dimensions, multi-tile edge geometry, and
a four-tile ROI crossing. Tests
decode every vector through the Python reference implementation and the native
backend when available. A deterministic payload mutation must be rejected by
strict checksum validation. Multi-tile encoding must also remain byte-for-byte
deterministic with 1, 2, and 4 worker threads.

These vectors freeze decoder expectations, not encoder byte identity. Encoders
may produce different valid Zstandard streams or mode decisions while decoding
to the required pixels.

`tests/conformance/extensions.json` additionally freezes `HIST`, `AROT`, and
combined protected-history behavior. It verifies random state access, exact
state hashes, successful one-shard repair, and rejection beyond the two-shard
repair budget. Future packs will add progressive layers, cancellation
checkpoints, and more malformed headers.
