# WIM2 format

WIM2 starts with a versioned fixed header, UTF-8 JSON metadata, and a fixed-size tile index. Every tile entry records geometry, codec mode, entropy ID, progressive layers, payload offset, compressed size, expanded size, and CRC32.

## Tile modes

- **Raw:** fallback when coding overhead would increase size.
- **Predictive:** reversible spatial prediction and residual coding.
- **Palette:** exact local palettes of up to 256 colors.
- **Wavelet:** reversible CDF 5/3 for lossless output and quantized CDF 9/7 for lossy output.

Automatic lossless selection chooses the smallest exact candidate. Lossy selection balances reconstructed distortion and encoded size. The decoder reads the recorded mode and never repeats classification.

## Independent tiles

Tiles are independently compressed and checksummed. ROI decoding can read only intersecting payloads, and corruption in one tile does not require trusting unrelated tiles.

## Extensions

Optional chunks are appended after the base image and located through an `XDIR` directory and fixed `XEND` trailer.

- `HIST`: indexed WIM2 history states.
- `AROT`: checksums and two GF(256) parity shards for bounded recovery.

This wiki page is an overview, not yet a frozen normative specification.
