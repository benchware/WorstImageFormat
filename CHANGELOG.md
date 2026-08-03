# Changelog

All notable WIMF changes are recorded here. The project follows semantic versioning for the Python package; container compatibility is documented separately.

## 2.1.0 — Unreleased

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

## 2.0.0 — 2026-08-03

### Added

- WIM2 hybrid Raw, Predictive, Palette, and Wavelet tiles.
- Portable C++17 kernels and pybind11 wheels.
- ROI decoding, high-bit-depth paths, native runtime diagnostics, WIM2 anti-rot, and chrono history.
- Cross-platform CI, visual codec reports, standalone C++ tests, and PyPI trusted-publishing workflows.

### Compatibility

- Existing WIMF v1, AWIF, legacy `ROT!`, and earlier WIM2 still images remain decodable.
- The supported Python floor is now 3.10.
