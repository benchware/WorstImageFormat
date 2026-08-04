# Roadmap

## Integration foundation

- [ ] Freeze the WIM2 normative specification.
- [x] Publish initial lossless decoder vectors for every WIM2 tile mode.
- [ ] Expand vectors across bit depths, alpha, ROI, extensions, and malformed files.
- [x] Add an experimental versioned C ABI with owned buffers and structured errors.
- [x] Add portable CMake build, install, and `find_package` support.
- [ ] Freeze the ABI and publish standalone signed C/C++ development archives.

## Application support

- [x] Pillow open/save plugin for grayscale, RGB, and RGBA WIM2 images.
- [ ] ImageMagick/GraphicsMagick coder.
- [ ] FFmpeg/libavcodec decoder.
- [ ] Linux MIME and thumbnail integration.
- [ ] Windows Explorer preview and thumbnails.
- [ ] macOS Quick Look support.

## Web and languages

- [ ] Single-threaded WebAssembly decoder on the web branch.
- [ ] JavaScript/WASM package.
- [ ] Rust bindings after the C ABI stabilizes.

GPU acceleration remains deferred until profiling identifies a real workload that benefits from it.
