# WIMF roadmap

WIM2 codec correctness and native CPU performance come first. The next major
goal is adoption: making the decoder straightforward for other applications to
embed without depending on Python.

## 1. Stabilize the integration contract

- [ ] Freeze and publish the WIM2 bitstream specification and compatibility rules.
- [x] Add initial committed lossless decoder vectors for all four tile modes.
- [x] Expand core vectors to grayscale, RGBA, 10/16-bit, odd edge tiles,
  multi-tile ROI, metadata, corruption rejection, and thread determinism.
- [x] Add HIST, AROT, protected-history, bounded-repair, and unrecoverable-damage vectors.
- [ ] Expand normative vectors to progressive layers, cancellation, and the
  complete malformed-input boundary.
- [x] Introduce an experimental, versioned C ABI over the portable C++17 core with
  plain option/result records, owned output buffers, and structured errors.
- [x] Freeze ABI v1 fields, enums, ownership, threading, errors, exception
  containment, cleanup, and version negotiation.
- [x] Add CMake build, install, and `find_package(WIMF)` rules independently of Python.
- [x] Add a C-ABI-only PGM/PPM process bridge for tools and languages that do not
  yet link the native library directly.
- [ ] Publish signed standalone C/C++ development archives in releases.
- [x] Document ABI resource limits, thread safety, ownership, errors, and decoder safety.
- [ ] Complete cancellation callbacks and licensing guidance for external SDK archives.

## 2. High-impact integrations

- [x] Ship an initial Pillow plugin so `Image.open("image.wimf")` and Pillow save workflows
  can use WIM2 naturally.
- [ ] Add an ImageMagick/GraphicsMagick coder backed by the stable C ABI.
- [ ] Add an FFmpeg/libavcodec WIM2 still-image decoder after the ABI and
  conformance suite are stable.
- [ ] Provide MIME registration and thumbnail integration for Linux desktops.
- [ ] Provide Windows Explorer thumbnail/preview support.
- [ ] Provide a macOS Quick Look extension.

## 3. Web and language ecosystems

- [ ] Build the memory-only synchronous core with Emscripten on the web branch.
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
