# WIMF roadmap

WIM2 codec correctness and native CPU performance come first. The next major
goal is adoption: making the decoder straightforward for other applications to
embed without depending on Python.

## 1. Stabilize the integration contract

- [x] Freeze the implemented WIM2 revision-2 base-container specification and compatibility rules.
- [x] Add initial committed lossless decoder vectors for all four tile modes.
- [x] Expand core vectors to grayscale, RGBA, 10/16-bit, odd edge tiles,
  multi-tile ROI, metadata, corruption rejection, and thread determinism.
- [x] Add HIST, AROT, protected-history, bounded-repair, and unrecoverable-damage vectors.
- [x] Cover the single-layer boundary, cancellation, and malformed-input limits;
  unsupported progressive layer counts are reserved and rejected.
- [x] Introduce an experimental, versioned C ABI over the portable C++17 core with
  plain option/result records, owned output buffers, and structured errors.
- [x] Freeze ABI v1 fields, enums, ownership, threading, errors, exception
  containment, cleanup, and version negotiation.
- [x] Add CMake build, install, and `find_package(WIMF)` rules independently of Python.
- [x] Add a C-ABI-only PGM/PPM process bridge for tools and languages that do not
  yet link the native library directly.
- [ ] Publish signed standalone C/C++ development archives in releases (SignPath
  policy and dormant workflow are ready; Foundation acceptance is external).
- [x] Document ABI resource limits, thread safety, ownership, errors, and decoder safety.
- [x] Expose portable progress/cancellation callbacks through both C++ and C APIs.
- [x] Package native SDK archives with WIMF/Zstandard licenses and distribution guidance.

## 2. High-impact integrations

- [x] Ship an initial Pillow plugin so `Image.open("image.wimf")` and Pillow save workflows
  can use WIM2 naturally.
- [x] Add an optional ImageMagick 7 decode coder backed by the stable C ABI.
- [x] Add an upstream-oriented FFmpeg/libavcodec WIM2 still-image decoder source kit.
- [x] Provide MIME registration and thumbnail integration for Linux desktops.
- [x] Provide native Windows Explorer thumbnail and preview-pane providers.
- [ ] Add a GraphicsMagick-specific coder and upstream the FFmpeg registration.
- [ ] Provide a macOS Quick Look extension.

## 3. Web and language ecosystems

- [x] Build and run the memory-only synchronous core conformance suite with Emscripten.
- [ ] Publish a small JavaScript/WASM decoder package before considering browser
  encoding or worker orchestration.
- [ ] Add Rust bindings around the C ABI once its versioning policy is proven.
- [ ] Consider other language bindings based on real integration requests.

## 4. Evidence required for adoption

- [ ] Maintain a public corpus benchmark against PNG, WebP, AVIF, JPEG, and JPEG XL
  at matched lossless or perceptual quality.
- [ ] Publish decode throughput, memory use, compression ratio, corruption
  containment, and platform/compiler details with reproducible commands.
- [ ] Keep fuzzing, sanitizers, malformed-input tests, and cross-platform decoder
  conformance blocking for releases.
- [ ] Provide minimal integration examples and an upstreaming checklist for each
  external project.

GPU acceleration, plugins inside the WIMF codec, and new container redesigns stay
deferred until profiling or adopter demand demonstrates a concrete need.
