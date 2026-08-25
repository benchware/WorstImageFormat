# WIMF roadmap

WIM2 codec correctness and native CPU performance come first. The next major
goal is adoption: making the decoder straightforward for other applications to
embed without depending on Python.

A consolidated audit of every significant open flaw lives in
`docs/known-flaws.md` (wiki mirror: *Known-Flaws*). Rate-distortion items in
section 5b target the largest one - compressed file size - first.

## 1. Integration foundation

- [x] Freeze the implemented WIM2 revision-2 base-container specification.
- [x] Publish initial lossless decoder vectors for every WIM2 tile mode.
- [x] Expand vectors across grayscale, RGBA, 10/16-bit, odd edge tiles, ROI,
  metadata, corruption rejection, and deterministic threading.
- [x] Add HIST, AROT, protected-history, bounded-repair, and unrecoverable-damage vectors.
- [x] Cover the single-layer boundary, cancellation, and malformed-input limits;
  unsupported progressive layer counts are reserved and rejected.
- [x] Add an experimental versioned C ABI with owned buffers and structured errors.
- [x] Freeze ABI v1 fields, enums, ownership, cleanup, threading, structured
  errors, exception containment, and version negotiation.
- [x] Add portable CMake build, install, and `find_package` support.
- [x] Add the C-ABI-only `wimf-native` PGM/PPM process bridge.
- [x] Document ABI resource limits, thread safety, ownership, errors, and decoder safety.
- [ ] Publish standalone signed C/C++ development archives (SignPath policy and
  dormant workflow are ready; Foundation acceptance is external).
- [x] Expose portable progress/cancellation callbacks through both C++ and C APIs.
- [x] Package native SDK archives with WIMF/Zstandard licenses and distribution guidance.

## 2. Application support

- [x] Pillow open/save plugin for grayscale, RGB, and RGBA WIM2 images.
- [x] Optional ImageMagick 7 decode coder backed by the C ABI.
- [x] Upstream-oriented FFmpeg/libavcodec WIM2 decoder source kit.
- [x] Linux MIME registration and thumbnail integration.
- [x] Native Windows Explorer thumbnail and preview-pane providers.
- [ ] GraphicsMagick-specific coder and upstream FFmpeg registration.
- [ ] macOS Quick Look support.
- [ ] Native Android build support (Termux/NDK): runtime dispatch already
  resolves the inactive-NEON report in issue #31; document the Android Bionic
  Zstandard `qsort_r` build note for native builds.
- [ ] Resolve progressive-layer design: either implement multi-layer coding or
  publish the reservation rationale in the WIM2 specification.

## 3. Web and languages

- [x] Build and run the single-threaded core conformance suite as WebAssembly.
- [ ] JavaScript/WASM package.
- [ ] Rust bindings after the C ABI stabilizes.
- [ ] Add other language bindings when real integration requests justify them.

## 4. Adoption evidence

- [ ] Maintain a public benchmark corpus against PNG, WebP, AVIF, JPEG, and JPEG XL.
- [ ] Publish reproducible throughput, memory, compression, corruption, platform,
  and compiler measurements.
- [x] Run automated SIMD kernel benchmarks (wimf-simd-bench) on every CI push,
  publishing per-OS job-summary reports and downloadable artifacts.
- [ ] Keep fuzzing, sanitizers, malformed-input tests, and cross-platform decoder
  conformance blocking for releases.
- [ ] Provide minimal examples and an upstreaming checklist for each integration.

## 5. Performance optimization

- [x] AVX2 (x86_64)
  - CRC-32 lookup-table acceleration and predictive left-filter vectorization.
  - Runtime-dispatched: AVX2 kernels are compiled into the binary and enabled
    via CPUID/XGETBV, so one build serves every x86-64 host. MSVC wheels that
    cannot scope per-file flags fall back to scalar automatically.
  - Benchmark targets: 2.5-3× speedup on Intel Haswell+ / AMD Zen+.
- [x] NEON (ARMv8+)
  - CRC-32 hardware acceleration (ARM CRC extension) and predictive left-filter vectorization.
  - Always enabled on aarch64 targets; no additional build flags required.
  - The optional CRC extension is probed at runtime (`getauxval(AT_HWCAP)`)
    and falls back to the scalar table when absent.
  - Benchmark targets: 2.5-3× speedup on Apple M1/M2, Raspberry Pi 4/5.
- [ ] Wavelet lifting optimization
  - Scalar-era reports show the double-precision lifting path with per-row and
    per-column heap allocations dominating Extreme encodes AND decodes:
    187 s encode and up to 213 s decode for 45 MP on an Ivy Bridge dual-core,
    versus 6 s for predictive-only encoding on the same machine.
- [ ] High-bit-depth predictive SIMD
  - Filter kernels cover 8-bit rows only; 10/16-bit images run the predictive
    path fully scalar even though mobile sensors commonly capture 10-bit.
- [x] Reuse Zstandard compression contexts across tile scoring: thread-local
  CCtx/DCtx via ZSTD_compressCCtx / ZSTD_decompressDCtx replace per-call
  construction; output stays byte-identical.
- [ ] AVX-512
  - Deferred until AVX2/NEON paths are measured and hardware
    support is widespread enough to justify the maintenance cost.

## 5b. Compression tuning

- [x] Content-adaptive wavelet quantization scaled by local tile energy.
- [x] Improved Zstandard compression levels (Fast 3, Balanced 9, Extreme 19).
- [x] Quadratic rate-distortion scoring for lossy tile selection.
- [x] Relaxed wavelet classification thresholds for smooth-gradient content.
- [x] Bitwise masking replacing modular arithmetic in the predictive codec.
- [x] Land color decorrelation: reversible mod-256 green differencing behind
  container flags bit 1 for 8-bit RGB/RGBA, with the Python decoder mirror
  added after run #180's failures pinpointed the missing inverse.
- [ ] YCoCg-with-offsets refinement of the color transform remains open.
- [x] Context-modeled entropy coding for wavelet subbands: an adaptive binary
  range coder (LZMA style, 11-bit probability models) replaces varint+zstd
  payloads behind reversible flags 3/4; lossy Q5 harness went from
  1.58x @ 25.48 dB to 2.31x @ 45.46 dB. Legacy unpackers retained for old files.
- [ ] Extend context-modeled entropy coding to prediction residuals;
  predictive and palette tiles still use generic Zstd payloads.
- [x] Rebuild the quality→quantizer ladder as a smooth, rate-monotonic curve.
  The 2.1/2.2 retunes eliminated the inversion (Extreme Q1 once recorded
  6.89x versus 17.31x at Q2); verified rate-monotonic across flat, gradient,
  and noisy content by `test_lossy_size_monotonic_in_quality`.
- [ ] Optional lossy chroma decimation for photographic tiers, reconstructed
  during decode without changing the WIM2 container.
- [x] Pin down the quality=10 contract: losslessness comes only from the
  explicit flag, never from quality or preset; documented in native-core and
  pinned by a native conformance test (the flag must flip the wavelet coding
  path, and explicit-lossless roundtrips stay bit-exact).
- [ ] Finish Extreme-preset scoring overhead reduction: candidates are now ranked
  with the cheaper Balanced Zstandard level and the winner is shipped at full
  strength; the remaining cost is the wavelet inverse still required for lossy
  distortion estimation (Auto Extreme was ~2× Predictive Extreme on Zen 2,
  ~13× on Ivy Bridge).
- [x] Subband-aware coefficient scanning for improved entropy coding: wavelet
  coefficients are reordered into dyadic subband sequence (LL, then HL/LH/HH
  per level) behind the levels-byte bit 7, clustering zeros for longer runs;
  Python decoder mirrored.
- [ ] Tile-size adaptation based on image content.


## 6. Quality-of-life improvements

- [x] Accept case-insensitive codec names in the Python API: `auto`, `Auto`,
  `Auto (hybrid)` and similar variants map to the same internal path.
- [ ] Implement ROI decode conformance test (currently returns `'encode'` error).
- [ ] Add `--file` or `--image` flag to the CLI to target a single image rather
  than scanning an entire directory.
- [ ] Expose progress feedback for long-running encodes (especially Extreme preset).
- [ ] Publish recommended configuration presets in the README based on real
  user benchmarks:
  - `quality=5, preset=Balanced, codec=auto` for general daily use.
  - `quality=5, preset=Balanced, codec=wavelet` for web/game delivery.
  - `quality=2, preset=Extreme, codec=auto` for archival storage.
  - `quality=4, preset=Fast, codec=auto` for high-speed batch work.
  - `lossless=True, preset=Balanced, codec=auto` for visually lossless quality.
- [ ] Publish standalone `wimf-native` CLI binary for systems without Python.

## 7. Platform validation

- [ ] Complete and publish benchmarks for:
  - x86_64 scalar baseline (completed: i5-4460, 2014)
  - x86_64 AVX2 on Kaby Lake or newer (kernel-level CI reports via wimf-simd-bench)
  - ARM NEON on Apple M1/M2 (kernel-level CI reports via wimf-simd-bench)
  - ARM NEON on Raspberry Pi 5
  - ARM NEON on Android/Termux (Snapdragon class); runtime dispatch resolves
    issue #31, native build guidance pending
- [ ] Ship SIMD-enabled Windows wheels: setuptools cannot scope `/arch:AVX2`
  per translation unit today; evaluate a clang-cl helper object or split-
  extension linkage so the largest install base gets acceleration.
- [ ] Maintain decoder conformance across all supported platforms.
- [ ] Document minimal hardware requirements and expected performance tiers.

Base16, Base32, and Base64 transport support is implemented. These encodings
help move WIMF through text-only systems but are not compression formats.

## 8. WIMF 3.0 candidates (breaking container redesign)

Nothing in this section lands in a 2.x release. Each item needs its own spec,
conformance vectors, and migration note before any code.

- [ ] Remove the 256x256 tile limit via quadtree tile splitting (AV1
  superblock style): stable regions stay one large tile while detailed areas
  subdivide.
- [ ] Embedded zerotree or bitplane coefficient coding (SPIHT style) so
  progressive-by-quality decode becomes real instead of the reserved layers
  field staying at 1.
- [ ] Chroma-from-luma decorrelation evaluated against fixed YCoCg-R across
  the photo corpus before either becomes the default.
- [ ] Perceptual quantization: contrast-sensitivity-weighted per-subband
  quantizers replacing the single global quantizer.
- [ ] First-class HDR and alpha: native 16-bit half float plus alpha handled
  in the core path rather than as container bolt-ons.
- [ ] Optional learned transform mode with a tiny decoder-side network, always
  shipped beside a scalar fallback so conformance stays testable.
- [ ] Carry-over wishlist blocked only by the container break: larger tile
  header fields, wider range-coder probability precision, per-tile quality maps.

GPU acceleration and plugins inside the codec remain deferred until profiling
or adopter demand identifies a concrete need. The breaking-container ideas in
section 8 are tracked separately so they cannot leak into 2.x releases.
