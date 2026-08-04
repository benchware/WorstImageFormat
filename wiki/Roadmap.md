# Roadmap

## Integration foundation

- [ ] Freeze the WIM2 normative specification.
- [ ] Publish decoder conformance vectors.
- [x] Add an experimental versioned C ABI with owned buffers and structured errors.
- [x] Add portable CMake build, install, and `find_package` support.
- [ ] Freeze the ABI and publish standalone signed C/C++ development archives.

## Application support

- [ ] Pillow plugin.
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
