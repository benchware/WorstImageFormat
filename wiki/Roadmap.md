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
- [ ] Reuse Zstandard compression contexts across tile scoring; ZSTD_compress
  constructs and frees a fresh context on every call, thousands of times per
  large image.
- [ ] AVX-512
  - Deferred until AVX2/NEON paths are measured and hardware
    support is widespread enough to justify the maintenance cost.

## 5b. Compression tuning

- [x] Content-adaptive wavelet quantization scaled by local tile energy.
- [x] Improved Zstandard compression levels (Fast 3, Balanced 9, Extreme 19).
- [x] Quadratic rate-distortion scoring for lossy tile selection.
- [x] Relaxed wavelet classification thresholds for smooth-gradient content.
- [x] Bitwise masking replacing modular arithmetic in the predictive codec.
- [ ] Apply a reversible RGB→YCoCg color transform before tile coding; channels
  are currently entropy-coded independently, leaving chroma correlation
  unexploited on every photographic image.
- [ ] Introduce context-modeled entropy coding tuned to prediction residuals
  and wavelet subbands; generic Zstd payloads are the main structural size gap
  versus modern image codecs.
- [ ] Rebuild the quality→quantizer ladder as a smooth, rate-monotonic curve;
  today Extreme records 6.89× at Q1 versus 17.31× at Q2 across every tested
  system, so lower quality currently produces larger files.
- [ ] Optional lossy chroma decimation for photographic tiers, reconstructed
  during decode without changing the WIM2 container.
- [ ] Pin down and document the quality=10 contract per preset: submitted
  reports show Fast Q10 remains lossy (~67.6 dB) while Balanced/Extreme Q10
  came out bit-exact; add a conformance test for whichever rule is chosen.
- [ ] Reduce Extreme-preset scoring overhead: all four candidate tile modes are
  Zstandard level 19-compressed per tile for scoring, and wavelet candidates add
  a full inverse transform; Auto Extreme costs about 2× Predictive Extreme even
  on Zen 2 (7.08 s versus 3.27 s for 45 MP).
- [ ] Subband-aware coefficient scanning for improved entropy coding.
- [ ] Tile-size adaptation based on image content.

## 6. Quality-of-life improvements

- [ ] Accept case-insensitive codec names in the Python API: `auto`, `Auto`,
  `Auto (hybrid)` and similar variants should map to the same internal path.
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

GPU acceleration, plugins inside the codec, and another container redesign
remain deferred until profiling or adopter demand identifies a concrete need.
