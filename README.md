<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/white.png">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/dark.png">
    <img alt="Worst Image Format Logo" src="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/dark.png" width="500">
  </picture>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3">
  <img src="https://img.shields.io/badge/python-3.8+-aff.svg" alt="Python: 3.8+">
  <img src="https://img.shields.io/badge/format-.wimf%20%7C%20.wif-orange" alt="Format: .wimf | .wif">
</p>

# WIMF: Worst Image Format

WIMF is a technically sophisticated image codec designed for high-precision data storage, data analysis, and VFX workflows. It prioritizes mathematical integrity and structural preservation over standard compatibility.

## Core Features

- **Tiled ROI Decoding**: High-speed Region of Interest extraction from massive (16K+) images without decompressing the full bitstream.
- **Self-Healing (Anti-Rot)**: Built-in XOR parity protection (block-level)
- **Chrono-Layers**: Delta-compressed historical state tracking, allowing a single file to store a complete undo history.
- **Progressive Loading**: Chunked bitstream structure allows image quality to improve gradually during transit.
- **Advanced Watermarking**: Invisible secret embedding directly within wavelet frequency layers.
- **VFX & HDR Support**: Full 10-bit and 16-bit precision pipelines with native support for 5-channel data (RGBA + Depth).

## The Technology

WIMF utilizes an advanced wavelet-based engine to outperform traditional block-based compression (like JPEG) in detail preservation:

- **Haar Wavelet Engine**: Multi-level frequency decomposition that prioritizes image structure over noise, resulting in painterly blurs rather than blocky artifacts at low bitrates.
- **Reversible YCoCg-R**: A high-efficiency color transform providing superior decorrelation and bit-perfect color accuracy.
- **LZMA Entropy Coding**: Deep dictionary-based compression for maximum data density.
- **Vectorized Math**: 100% NumPy-based implementation for high-speed multi-threaded processing.

## Developer Suite

- **wimf Python Library**: Enterprise-grade API featuring stateful `WIMFDecoder` and `WIMFEncoder` classes.
- **wimf-convert**: Robust CLI tool for batch conversion, format migration, and performance benchmarking.
- **wimf-cat**: Native 24-bit TrueColor terminal image renderer.
- **wimf-meta**: Surgical metadata editor for non-destructive header updates.

## Installation

```bash
pip install wimf
```

## Quick Start

```python
import wimf
from PIL import Image

# High-level opening
img = wimf.open("photo.wimf")
img.pil.show()

# High-level saving
wimf.save("output.wimf", img.pil, quality=7, anti_rot=True)
```

## License
WIMF is licensed under the GPL 3.0.
