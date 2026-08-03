# Changelog

All notable WIMF changes are recorded here. The project follows semantic versioning for the Python package; container compatibility is documented separately.

## 2.0.0 — Unreleased

### Added

- WIM2 hybrid Raw, Predictive, Palette, and Wavelet tiles.
- Portable C++17 kernels and pybind11 wheels.
- ROI decoding, high-bit-depth paths, native runtime diagnostics, WIM2 anti-rot, and chrono history.
- Cross-platform CI, visual codec reports, standalone C++ tests, and PyPI trusted-publishing workflows.

### Compatibility

- Existing WIMF v1, AWIF, legacy `ROT!`, and earlier WIM2 still images remain decodable.
- The supported Python floor is now 3.10.
