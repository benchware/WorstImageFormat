# WIMF known-flaws audit

Snapshot of every significant open flaw, ordered by impact inside each
category. Evidence comes from the committed scalar-era benchmarks
(`benchmarkinfo/no avx2/`), issue #31, and source review of the v2 core.
Fixes are tracked through the roadmap checkboxes; this page is the index.

Severity tags: **[P0]** viability-critical, fix before any adoption pitch;
**[P1]** severe, bounded impact; **[P2]** medium; **[P3]** backlog.
None of the entries below are integrity or security bugs - decoded pixels,
determinism, corruption rejection, and memory guards all audited clean
(section E).

## A. Rate-distortion (file size) - the headline flaw

- **[P0] A1 Whole-ladder size gap.** Improved: monotonic RD scoring (A4),
  subband-aware wavelet coefficient ordering (A3 stage 1), channel
  decorrelation (A2), and the scoring divisor retune (8.0→16.0, adds
  intermediate lossy ladder steps) all landed; remaining gap is the
  context-modeled entropy stage. Photographic 45 MP results: Auto Fast
  39.6 MB (3.36x), best lossless 24.6 MB (5.41x), Wavelet Balanced ~13.5 MB
  (9.9x), best-case Extreme 7.7 MB (17.31x) at minutes of encode cost. Even
  the Extreme optimum is far above what modern codecs reach at comparable
  quality; Fast is barely smaller than half-rate JPEG territory.
- **[P0] A2 No color decorrelation.** RGB channels are entropy-coded
  independently (`encode_predictive` loops channels; wavelet planes are built
  per channel). A reversible RGB→YCoCg transform is the standard first win on
  photographic content. Landed: native encoder/decoder plus the Python decoder mirror (the mirror was exactly what run #180s failures exposed). YCoCg-with-offsets refinement pending.
- **[P0] A3 Generic entropy stage.** Tile payloads are Zstandard bytes of raw
  prediction residuals or zigzag varint coefficients. No context modeling of
  residuals/subbands - the structural advantage modern image codecs exploit.
- **[P1] A4 Coarse quantizer dead zone.** Monotonic scoring (A4) and the
  divisor retune 8.0→16.0 fixed the old non-monotonicity and added intermediate
  lossy steps; the photo-pattern sweep still shows a 34-43 dB gap where no
  quality setting lands. Cause: the adaptive quantizer (`sqrt(energy)/40`,
  clamped 0.5-2.0) is bimodal between heavy and light regimes. Fix requires
  continuous quantizer interpolation in code, not constant tuning.
- **[P2] A5 Per-tile framing overhead.** Default 128 px tiles give ~2.8k
  independent Zstd frames per 45 MP encode (per scored mode), with no
  cross-tile context or dictionaries.

## B. Performance

- **[P1] B1 Wavelet lifting (scalar doubles, per-line allocations).** Dominates
  Extreme encodes AND decodes: 187 s encode, up to 213 s decode for 45 MP on
  an Ivy Bridge dual-core, versus 6 s predictive-only on the same machine.
- **[P1] B2 Extreme search tax.** All four candidate modes are Zstd-19-compressed
  per tile for scoring; wavelet candidates add a full inverse transform purely
  for distortion estimation. Auto Extreme ≈ 2× Predictive Extreme on Zen 2,
  ≈ 13× on Ivy Bridge. Improved: candidates now rank at the Balanced Zstandard level; only the winner ships at full strength.
- **[P1] B3 Zstd context churn.** `ZSTD_compress` constructs and frees a fresh
  context on every call; thousands of calls per large image across candidates. Fixed: thread-local reused contexts landed on the acceleration branch.
- **[P2] B4 High-bit-depth paths bypass SIMD.** Filter kernels are 8-bit only;
  10/16-bit predictive runs fully scalar despite mobile sensors capturing
  10-bit.
- **[P2] B5 `classify_tile` palette probe.** Builds a string-keyed hash entry per
  sampled pixel; measurable next to the tile work it gates.
- **[P1] B6 Windows pip wheels ship scalar-only.** setuptools cannot scope
  `/arch:AVX2` per translation unit, so the largest install base gets none of
  the acceleration (native/CMake builds are unaffected).

## C. Semantics, API, format

- **[P0] C1 Undefined quality=10 contract.** Submitted reports show Fast Q10
  stays lossy (~67.6 dB) while Balanced/Extreme Q10 came out bit-exact. No
  documented rule for where the lossless boundary sits per preset; needs one
  defined contract plus a conformance test.
- **[P2] C2 Progressive layers reserved but always rejected.** Container carries
  a layers field; encoder writes 1 and parser rejects anything else. Design
  debt: implement multi-layer coding or publish the reservation rationale.
- **[P3] C3 ROI decode conformance gap**, no published recommended presets, and
  no progress feedback for long Extreme encodes (roadmap section 6 items).

## D. Platform and packaging

- **[P2] D1 Android/Termux guidance pending.** Runtime dispatch resolves issue
  #31's inactive-NEON half; NDK/Termux build notes (including the Bionic
  Zstandard `qsort_r` workaround) still need documenting.
- **[P3] D2 Signed SDK archives** not yet published (SignPath workflow dormant).
- **[P3] D3 Integration backlog:** GraphicsMagick coder, upstream FFmpeg
  registration, macOS Quick Look.

## E. Audited non-flaws

Verified working during this review - do not chase ghosts here:
deterministic threaded encoding, per-tile CRC corruption rejection, bounded
repair/anti-rot, cancellation semantics, allocation/output-limit guards,
WASM conformance suite, ASan/UBSan fuzz coverage.

- Generated 2026-08-23. Update entries (or check them off in the roadmap)
as fixes land; keep both mirrors identical.
