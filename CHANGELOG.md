# Changelog

All notable WIMF changes are recorded here. The project follows semantic versioning for the Python package; container compatibility is documented separately.

## 2.2.0 - Unreleased

- Filled the lossy quality dead zone: tile scoring now evaluates a second
  wavelet candidate at 0.9x quantizer scale. Each payload stores its own
  quantizer, so no format change is needed and the decoder is untouched; the
  extra sub-step lands between ladder rungs that previously jumped ~10 dB.
  Lossless encodes are unchanged and bit-identical.
- Added a natural-image pattern (three octaves of 1/f-spectrum value noise) to
  the RD sweep corpus as the closest deterministic proxy for real photographs.
- Retuned the lossy rate-distortion scoring divisor default from 8.0 to 16.0
  after an RD sweep on mixed-frequency content: the quality ladder gains
  intermediate lossy steps (notably Q4) with no regressions on any corpus
  pattern. Lossless output is bit-identical.
- Added a photo-like mixed-frequency pattern to the RD sweep corpus
  (`tools/wimf_rd_sweep.cpp`) and refreshed the tuning workflow matrix around
  the new default.
- Made WIM2 the sole recommended authoring format.
- Deprecated WIMF v1, the `.wif` filename alias, AWIF/v1 chrono, `ROT!`, watermark, legacy mip/depth,
  `wimf-convert`, and `wimf-meta` authoring surfaces ahead of WIMF 3.0.
- Retained read-only compatibility and added a committed AWIF-era decode fixture.
- Limited CodeQL to first-party production code and documented bundled Zstandard 1.5.7 provenance.
- Unified public native/Python option validation and removed AWIF from performance benchmarks.
- Added NEON (ARMv8) and AVX2 (x86-64) SIMD acceleration for CRC-32 checksums and predictive filter encoding.
- Added content-adaptive wavelet quantization that scales with local tile detail.
- Improved Zstandard compression levels for all search presets (Fast 1→3, Balanced 6→9, Extreme 15→19).
- Improved lossy tile selection with quadratic rate-distortion scoring.
- Relaxed wavelet tile classification thresholds for better compression of smooth content.
- Replaced modular-arithmetic operations with bitwise masking in the predictive codec.
- Reworked SIMD acceleration around runtime CPU dispatch: AVX2 (x86-64) and NEON
  (ARMv8) kernels are compiled into dedicated translation units and selected per
  host via CPUID/XGETBV or `getauxval`, with scalar fallbacks when a feature is
  absent, so a single binary runs safely everywhere. The ARM CRC-32 extension is
  probed through `getauxval(AT_HWCAP)` instead of requiring a compile-time target.
- Removed the `WIMF_ENABLE_AVX2` CMake option; AVX2 is now always available to
  capable CPUs without rebuilding (MSVC builds scope `/arch:AVX2` to the kernel
  translation unit only).
- Added a native SIMD kernel benchmark (`tools/wimf_simd_bench.cpp`,
  `WIMF_BUILD_BENCHMARKS`) that times scalar/AVX2/NEON filter and CRC-32
  kernels plus a synthetic-image lossless round trip, emitting Markdown for CI
  job summaries; CI publishes per-OS reports on every run.
- Reduced Extreme preset encode cost by ranking tile candidates at the cheaper
  Balanced Zstandard level and recompressing only the winning tile at full
  strength (shipped files keep full-level compression).
- CI job summaries now render human-readable benchmark tables instead of raw
  JSON, with per-runner hardware caveats stated inline.
- Native WIM2 encodes of 8-bit RGB/RGBA now decorrelate color before tile coding
  (reversible green differencing stored via container flags bit 1), shrinking
  photographic payloads. The Python reference decoder understands the flag too;
  decoding such files requires this release or newer.
- Fixed the rate-distortion scoring curve: the distortion penalty now scales
  monotonically with quality, eliminating the Extreme-preset cliff where Q1
  produced larger files than Q2.
- Wavelet coefficients are reordered into dyadic subband sequence (levels-byte
  bit 7) before entropy coding, clustering zeros for measurably smaller wavelet
  tiles; Python decoder mirrored. Requires this release or newer.

## 2.1.0 - 2026-08-03

### Added

- Complete memory-only WIM2 encode/decode orchestration in the portable C++17 core.
- Structured no-throw status results, deterministic synchronous/threaded execution policies, and native ROI reconstruction.
- Pinned portable Zstandard 1.5.7 sources for Python-independent native embedding.
- A synchronous execution path suitable for a future Emscripten binding without introducing a browser bundle.
- A unified `wimf` command with encode, decode, info, runtime, and view workflows.
- Memory-oriented `wimf.encode()`, `wimf.decode()`, and `wimf.inspect()` convenience APIs.
- WIMF Studio with encode/compare, tile inspection, ROI, metadata, anti-rot/history, and codec-lab panels.
- Strict Base64/data-URL transport helpers and deterministic corruption diagnostics.
- Native image comparison, payload-preserving WIM2 metadata rewriting, and tile-level progress/cancellation callbacks.

### Changed

- Python now dispatches each WIM2 encode or decode as one native operation while retaining the reference fallback.
- Native runtime diagnostics report orchestration support and available execution policies.
- The desktop viewer now has file, fit, actual-size, and metadata controls plus a graphical file picker.
- `wimf-view` now opens Studio while remaining a compatible command; headless CLI tools do not import Tkinter.

## 2.0.0 - 2026-08-03

### Added

- WIM2 hybrid Raw, Predictive, Palette, and Wavelet tiles.
- Portable C++17 kernels and pybind11 wheels.
- ROI decoding, high-bit-depth paths, native runtime diagnostics, WIM2 anti-rot, and chrono history.
- Cross-platform CI, visual codec reports, standalone C++ tests, and PyPI trusted-publishing workflows.

### Compatibility

- Existing WIMF v1, AWIF, legacy `ROT!`, and earlier WIM2 still images remain decodable.
- The supported Python floor is now 3.10.
