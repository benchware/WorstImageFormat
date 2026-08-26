# WIM2 format specification

This document defines the normative WIM2 revision-2 base container implemented
by WIMF 2.2. All integers are unsigned little-endian. Readers must reject
reserved values unless a later compatible specification assigns them.

## Base container

The 26-byte fixed header is followed by `metadata_size` bytes of UTF-8 JSON and
then `tile_count` 32-byte index records.

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | ASCII `WIM2` |
| 4 | 1 | container version, exactly `2` |
| 5 | 1 | flags |
| 6 | 1 | bit depth: 8, 10, or 16 |
| 7 | 1 | channel count, 1–16 |
| 8 | 4 | width |
| 12 | 4 | height |
| 16 | 2 | tile size, 16–256 |
| 18 | 4 | metadata size |
| 22 | 4 | tile count |

Each tile record contains `x:u16`, `y:u16`, `width:u16`, `height:u16`,
`mode:u8`, `entropy:u8`, `layers:u8`, one reserved zero byte, `offset:u64`,
`compressed_size:u32`, `expanded_size:u32`, and `crc32:u32`, in that order.

Payloads do not overlap semantically and each tile is independently decodable.
Current modes are Raw (0), Predictive (1), Palette (2), and Wavelet (3);
entropy IDs are None (0), Zstandard (1), and Range-coded (2, predictive
residuals only). WIMF 2.2 writes and accepts exactly one layer. Other layer
counts are reserved and rejected rather than silently misdecoded.

### Why the layers field stays at 1

The `layers` byte reserves room for quality-progressive coding: multiple
refinement passes per tile that a decoder could stop after to get an early
coarse image. Multi-layer coding was considered and deferred for WIM2:

- Tiles are already independently decodable; a progressive client gets most
  of the practical benefit by decoding tiles in priority order rather than
  by partially decoding each tile.
- Layer bookkeeping would touch every container invariant at once: per-layer
  offsets and checksums in the index, AROT shard repair across layers, ROI
  intersection semantics, and the raw-size validation limits.
- The adaptive range coder with subband-aware contexts captures the size
  wins that motivated layered refinement at a fraction of the complexity.

True embedded progressive streams (zerotree or bitplane coding) are tracked
as a WIMF 3.0 item, where the container break makes layer-native design
cheaper than retrofitting this format. Until then `layers != 1` is rejected;
the value survives so old files never need migration if 3.0 changes course.

Readers validate dimensions, tile coverage, mode and entropy IDs, offsets,
expanded-size limits, metadata limits, and checksums before decoding. ROI
decoding reads only intersecting entries.

## Coding modes

- Raw stores pixel bytes when codec overhead would increase size.
- Predictive selects a spatial predictor per channel row and compresses reversible residuals; residuals ship Zstandard-compressed or, when smaller, as an adaptive range-coded stream (entropy ID 2).
- Palette stores up to 256 local colors plus one-byte indices.
- Wavelet uses reversible CDF 5/3 for lossless data and quantized CDF 9/7 for lossy data. Coefficients are packed by an adaptive binary range coder (reversible flags 3/4 single-context, 6 with per-subband contexts); zero-run varint packing remains decodable via flags 0-2.

`auto` classifies each tile to shortlist candidates. Lossless selection uses actual encoded size. Lossy selection combines encoded size and reconstructed distortion. The chosen mode is always recorded; decoders never classify.

## Optional extensions

Extensions are appended after the base payload and located by a fixed `XEND` trailer. The checksummed `XDIR` directory contains four-byte chunk types, offsets, sizes, checksums, and flags. Readers that do not understand extensions can decode the original base image.

- `HIST` stores an indexed collection of bounded, independently decodable WIM2 states. State count, length, and CRC are validated before use.
- `AROT` stores checksums and two GF(256) parity shards over the protected prefix. It detects arbitrary damaged shards and can recover at most two; larger failures are rejected.

Extension counts, individual sizes, history state counts, offsets, and aggregate expansions are bounded. Unknown chunks are preserved as opaque data by readers that support directory inspection and otherwise ignored for primary-image decoding.

## Compatibility

The decoder recognizes WIM2, WIMF v1, AWIF, the `.wif` filename alias, and the legacy `ROT!` wrapper. WIMF 2.2 deprecates all legacy authoring and `.wif` output; WIMF 3.0 removes those writers while retaining read-only compatibility. New output uses the `.wimf` extension and WIM2 chunks for chrono history and anti-rot protection.
