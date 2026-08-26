# WIMF 3.0 format specification (draft, codename oxygen)

Status: **draft for review**. No code on this branch implements any of it.
Each section needs conformance vectors and a migration note before a C++
implementation lands. Container compatibility with WIM2 is intentionally
broken; WIM2 files keep decoding through the existing v2 path forever.

## Design goals

1. Remove structural limits that WIM2 froze in place (tile size, header
   widths, probability precision) rather than accumulating more reserved
   bytes.
2. Make progressive-by-quality real: an embedded stream that decoders can
   truncate, not a layers counter pinned to 1.
3. Keep the property that made WIMF robust so far: every tile independently
   checksummed, decodable, and validated before pixel work begins.

## Container

- Magic `WIM3`, version byte 3. Old parsers reject cleanly at the magic;
  new parsers reject `WIM2` explicitly.
- Header grows: width/height become u32 fields kept, tile count becomes
  u32 kept, plus a u64 total payload length for streaming validation.
- Tile records drop to a fixed 40-byte layout: x:u32, y:u32, w:u32, h:u32,
  mode:u8, entropy:u8, transform:u8, quality_map:u8, offset:u64,
  packed_size:u64, crc32c:u32, reserved:u24. The old 256x256 ceiling is
  gone; see quadtree below.

## Quadtree tile splitting

Replaces fixed-grid tiling. The encoder builds a split tree per image:

- A leaf tile may be any power-of-two-aligned rectangle down to 16x16 and
  up to the full image; no 256 cap.
- Split decisions come from the same classifier that shortlists candidate
  modes today, extended with a rate cost per split level.
- The tree is serialized once per image (max 4 children per node, depth
  capped at 12) and checksummed; tile records reference leaf indices.
- Decoders reconstruct coverage from the tree instead of validating a
  uniform grid, which removes the `x % tile_size` checks entirely.

## Embedded coefficient streams

Wavelet tiles switch from "decode everything or nothing" to embedded
bitplane coding with zerotree significance ordering (SPIHT-family):

- Truncating a tile's payload mid-stream yields a valid lower-quality
  reconstruction of that tile; a length prefix per refinement pass lets
  decoders stop early.
- Progressive decode = decode all LL passes first, then refine. The
  container needs no layer bookkeeping; progressiveness lives inside each
  tile's bitstream.
- The range coder stays (11-bit probabilities), but precision widens to
  15-bit with per-band, per-bitplane contexts carried over from the 2.3
  work.

## Color and perception

- Chroma-from-luma evaluated as the default decorrelation against fixed
  YCoCg-R across the photo corpus; winner ships, loser stays behind a
  transform enum value.
- Quantization becomes per-subband and perceptually weighted (contrast
  sensitivity function baseline); the single global quantizer byte becomes
  a per-tile quality map reference into one shared quant table.

## HDR and alpha

- Sample formats: u8, u10, u12, u16, f16. Bit depth byte becomes an enum.
- Alpha is a channel like any other but flagged in the header so lossy
  transforms can treat it as straight or premultiplied per a header bit.

## Learned transform (optional, gated)

A tiny decoder-side network for photographic tiles, shipped beside a
scalar fallback path so conformance vectors stay runnable everywhere.
Encoder-side search picks whichever wins RD. This item lands last and may
slip to 3.1 without breaking the container.

## Migration and conformance

- Every feature above ships with: golden encode vectors, truncation
  vectors for embedded streams, corruption-rejection vectors, and a
  Python-mirror decoder note (native-only features must fail loudly).
- The 3.0 release checklist adds: WIM2 corpus regression (all 2.x files
  decode identically through the legacy path), fuzzing gate on the new
  parser, and quadtree coverage sweeps (degenerate 1-pixel leaves up to
  full-image leaves).

## Open questions

1. Does CRC32C replace CRC32 for tile payloads in 3.0, or stay identical
   to ease cross-version tooling?
2. Metadata chunk format: carry WIM2's JSON blob unchanged?
3. Do extensions (XDIR/XEND) survive as-is?
