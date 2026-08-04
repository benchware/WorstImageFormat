# WIM2 conformance vectors

`tests/conformance/vectors.json` is the first language-neutral decoder
conformance pack. Each WIM2 payload is Base64-wrapped only so it can be reviewed
and copied through text systems. The manifest records:

- container SHA-256;
- exact decoded-pixel SHA-256;
- dimensions, channels, and bit depth;
- the required recorded tile mode.

The pack contains lossless Raw, Predictive, Palette, and Wavelet vectors. Tests
decode every vector through the Python reference implementation and the native
backend when available. A deterministic payload mutation must be rejected by
strict checksum validation.

These vectors freeze decoder expectations, not encoder byte identity. Encoders
may produce different valid Zstandard streams or mode decisions while decoding
to the required pixels. Future packs will add 10/16-bit samples, alpha, odd edge
tiles, multi-tile ROI, extensions, progressive layers, and malformed headers.
