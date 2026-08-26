# WIMF 3.0 format specification (draft, codename oxygen)

Status: **phases 1-3 implemented on this branch**. The container, split
tree, Raw / Predictive-RC / embedded-wavelet tile modes, u8-u16 sample
depths, truncation-based progressive decode, and quantized-bitplane lossy
coding all ship. EXIF tags round-trip through the container metadata block
(`exif` key: integer-tag strings to values; Pillow interop included).
Remaining future work: chroma-from-luma, perceptual (CSF-weighted)
quantization, and the optional learned transform - each needs corpus
evaluation. Container compatibility with WIM2 is intentionally broken;
WIM2 files keep decoding through the existing v2 path forever.

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

- A leaf tile may be any rectangle from 1 pixel up to the full image; the
  `max_tile` header field (16..4096) caps the longest edge a leaf may have.
- Split rule, identical on writer and reader: while either edge exceeds
  `max_tile`, emit an internal node. Nodes are tagged: 1 = vertical split
  (left/right halves), 2 = horizontal split (top/bottom halves), 3 = quad
  when both edges exceed the cap. A dimension only splits when it exceeds
  the cap, so extreme aspect ratios terminate without degenerate children.
- The tree serializes pre-order, one byte per node, and is checksummed by
  the container's payload-length validation; decoders rebuild coverage from
  it and require the leaf sequence to match the tile records one-to-one,
  which removes the old `x % tile_size` checks entirely.

## Implementation status

Phase 1 (this branch), all with full structural validation and CRC32C:

- Container parse/write with exact-tree coverage enforcement, record-vs-tree
  geometry agreement, payload non-overlap, and total-length checks.
- Tile modes Raw (0) and Predictive (1, entropy byte 2 reusing the v2 range
  coder for residuals). Lossless only; mode selection picks the smaller of
  raw vs predictive per leaf.
- Corruption-rejection vectors: magic, version, depth, max_tile bound,
  metadata/tree length overflow, reserved-byte policy, payload CRC,
  truncation at every structural boundary, and WIM2-magic rejection.

Phase 2 (this branch):

- Tile mode Wavelet (2): lossless CDF 5/3 coefficients coded one magnitude
  bitplane at a time into independently flushed range-coder segments.
  Significance decisions use per-subband models keyed by parent
  significance (zerotree-style context); magnitudes are coded sign-magnitude,
  never raw two's complement.
- Progressive decode: payloads truncate at plane boundaries into valid
  coarser images, and decoders accept an explicit target-plane cap. Both
  paths are pinned by tests asserting capped-decode equals truncated-file
  decode.
- Sample depths u8, u10, u12, u16 (u10/u12 ride little-endian u16 samples);
  f16 stays reserved and rejected.

Phase 3 (this branch):

- Lossy coding via quantized bitplanes: the tile payload header carries a
  `quant_shift` byte (0-14); coefficient magnitudes are coded after an
  arithmetic right shift by that amount and shifted back on
  reconstruction - a uniform dead-zone scalar quantizer that reuses the
  entire embedded machinery. Quality 1-10 maps to the shift; quality 10 or
  the lossless flag keeps every plane. Lossy payloads truncate
  progressively exactly like lossless ones.
- EXIF interop: camera tags captured from Pillow sources ride the metadata
  JSON under `exif` and rebuild into `PIL.Image.Exif` on decode, so
  WIMF-to-JPEG/TIFF saves re-attach them automatically.

Future work in order: chroma-from-luma + perceptual quantization (needs a
photo-corpus RD harness), learned transform behind a scalar fallback.

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

1. Resolved: tile payloads use CRC32C (Castagnoli); the v2 CRC32 remains
   only in the legacy path.
2. Metadata chunk format: carry WIM2's JSON blob unchanged? (leaning yes)
3. Do extensions (XDIR/XEND) survive as-is?
