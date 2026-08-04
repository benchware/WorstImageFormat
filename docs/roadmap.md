# WIMF roadmap

WIM2 codec correctness and native CPU performance come first. The next major
goal is adoption: making the decoder straightforward for other applications to
embed without depending on Python.

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

## 3. Web and languages

- [x] Build and run the single-threaded core conformance suite as WebAssembly.
- [ ] JavaScript/WASM package.
- [ ] Rust bindings after the C ABI stabilizes.
- [ ] Add other language bindings when real integration requests justify them.

## 4. Adoption evidence

- [ ] Maintain a public benchmark corpus against PNG, WebP, AVIF, JPEG, and JPEG XL.
- [ ] Publish reproducible throughput, memory, compression, corruption, platform,
  and compiler measurements.
- [ ] Keep fuzzing, sanitizers, malformed-input tests, and cross-platform decoder
  conformance blocking for releases.
- [ ] Provide minimal examples and an upstreaming checklist for each integration.

## 5. Performance optimization

- [ ] AVX2 (x86_64)
  - Benchmark targets: 2.5-3× speedup on Intel Haswell+ / AMD Zen+
  - Measured baseline: i5-4460 (Haswell, scalar): 26.7 MP/s (Fast preset),
    9.1 MP/s (Wavelet Balanced), 3.4 MP/s (Extreme Q2)
  - Implementation deferred until profiling confirms real-world gain
- [ ] NEON (ARMv8+)
  - Benchmark targets: 2.5-3× speedup on ARMv8+ (Apple M1/M2, Raspberry Pi 4/5,
    Android, ChromeOS)
  - Minimum acceptable Raspberry Pi 5 target: 25+ MP/s (Fast), 10+ MP/s
    (Wavelet Balanced), 5+ MP/s (Extreme)
- [ ] AVX-512
  - Experimental; deferred until AVX2/NEON paths are stable and hardware
    support is widespread enough to justify the maintenance cost.
  - Thermal and performance-regression risks documented.

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
  - x86_64 AVX2 on Kaby Lake or newer
  - ARM NEON on Apple M1/M2
  - ARM NEON on Raspberry Pi 5
- [ ] Maintain decoder conformance across all supported platforms.
- [ ] Document minimal hardware requirements and expected performance tiers.

Base16, Base32, and Base64 transport support is implemented. These encodings
help move WIMF through text-only systems but are not compression formats.

GPU acceleration, plugins inside the codec, and another container redesign
remain deferred until profiling or adopter demand identifies a concrete need.
