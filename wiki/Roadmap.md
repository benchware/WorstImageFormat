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
- [ ] Publish standalone signed C/C++ development archives.
- [x] Expose portable progress/cancellation callbacks through both C++ and C APIs.
- [x] Package native SDK archives with WIMF/Zstandard licenses and distribution guidance.

## 2. Application support

- [x] Pillow open/save plugin for grayscale, RGB, and RGBA WIM2 images.
- [ ] ImageMagick/GraphicsMagick coder backed by the C ABI.
- [ ] FFmpeg/libavcodec WIM2 still-image decoder.
- [ ] Linux MIME and thumbnail integration.
- [ ] Windows Explorer preview and thumbnails.
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

Base16, Base32, and Base64 transport support is implemented. These encodings
help move WIMF through text-only systems but are not compression formats.

GPU acceleration, plugins inside the codec, and another container redesign
remain deferred until profiling or adopter demand identifies a concrete need.
