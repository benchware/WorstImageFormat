# WIM2 format overview

This document describes the implemented WIM2 container. It is an engineering overview, not yet a frozen standards document. All integers are little-endian.

## Base container

The fixed header records `WIM2`, version 2, flags, bit depth, channel count, image dimensions, tile size, metadata length, and tile count. UTF-8 JSON metadata follows, then a fixed-size tile index.

Each tile entry records geometry, codec mode, entropy-coder ID, progressive-layer count, payload offset, compressed and expanded sizes, and CRC32. Payloads do not overlap semantically and each tile is independently decodable. Current modes are Raw (0), Predictive (1), Palette (2), and Wavelet (3); entropy IDs are None (0) and Zstandard (1).

Readers validate dimensions, tile coverage, mode and entropy IDs, offsets, expanded-size limits, metadata limits, and checksums before decoding. ROI decoding reads only intersecting entries.

## Coding modes

- Raw stores pixel bytes when codec overhead would increase size.
- Predictive selects a spatial predictor per channel row and compresses reversible residuals.
- Palette stores up to 256 local colors plus one-byte indices.
- Wavelet uses reversible CDF 5/3 for lossless data and quantized CDF 9/7 for lossy data. Coefficients use zero runs and zigzag varints before entropy coding.

`auto` classifies each tile to shortlist candidates. Lossless selection uses actual encoded size. Lossy selection combines encoded size and reconstructed distortion. The chosen mode is always recorded; decoders never classify.

## Optional extensions

Extensions are appended after the base payload and located by a fixed `XEND` trailer. The checksummed `XDIR` directory contains four-byte chunk types, offsets, sizes, checksums, and flags. Readers that do not understand extensions can decode the original base image.

- `HIST` stores an indexed collection of bounded, independently decodable WIM2 states. State count, length, and CRC are validated before use.
- `AROT` stores checksums and two GF(256) parity shards over the protected prefix. It detects arbitrary damaged shards and can recover at most two; larger failures are rejected.

Extension counts, individual sizes, history state counts, offsets, and aggregate expansions are bounded. Unknown chunks are preserved as opaque data by readers that support directory inspection and otherwise ignored for primary-image decoding.

## Compatibility

The decoder recognizes WIM2, WIMF v1, AWIF, and the legacy `ROT!` wrapper. WIMF 2.2 deprecates all legacy authoring; WIMF 3.0 removes those writers while retaining read-only compatibility. New output uses WIM2 chunks for chrono history and anti-rot protection.
