# Conformance vectors

The committed `tests/conformance/vectors.json` pack allows independent decoders
to verify WIM2 behavior without using the WIMF encoder.

Each Base64-wrapped vector records its container SHA-256, decoded pixel SHA-256,
dimensions, channel count, bit depth, and required tile mode. The initial pack
covers exact lossless Raw, Predictive, Palette, and Wavelet tiles plus checksum
rejection after payload corruption.

Encoder output is not required to be byte-identical: alternative valid
Zstandard streams and mode decisions are allowed. Decoder pixels and safety
behavior are the compatibility contract.
