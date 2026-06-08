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

# WIMF: Worst IMage Format

WIMF is an experimental image format that provides advanced features like self-healing, undo history, and fast region loading. It uses modern color math and wavelets to store your images with high precision and density.

## Core Features

- **Tiled ROI Decoding**: High-speed Region of Interest extraction from massive (16K+) images without decompressing the full bitstream.
- **Self-Healing (Anti-Rot)**: Built-in XOR parity protection (block-level)
- **Chrono-Layers**: Delta-compressed historical state tracking, allowing a single file to store a complete undo history.
- **Progressive Loading**: Chunked bitstream structure allows image quality to improve gradually during transit.
- **Advanced Watermarking**: Invisible secret embedding directly within wavelet frequency layers.
- **High Precision & Extra Channels**: Full 10-bit and 16-bit precision pipelines with native support for 5-channel data (RGBA + Depth).

## The Technology

WIMF utilizes an advanced wavelet-based engine to outperform traditional block-based compression (like JPEG) in detail preservation:

- **Haar Wavelet Engine**: Multi-level frequency decomposition that prioritizes image structure over noise, resulting in painterly blurs rather than blocky artifacts at low bitrates.
- **Reversible YCoCg-R**: A high-efficiency color transform providing superior decorrelation and bit-perfect color accuracy.
- **LZMA Entropy Coding**: Deep dictionary-based compression for maximum data density.
- **Vectorized Math**: 100% NumPy-based implementation for high-speed multi-threaded processing.

## Developer Suite

- **wimf Python Library**: API featuring stateful `WIMFDecoder` and `WIMFEncoder` classes.
- **wimf-convert**: Robust CLI tool for batch conversion, format migration, and performance benchmarking.
- **wimf-cat**: View WIMF images in the CLI.
- **wimf-meta**: Metadata editor for non-destructive header updates.

## Installation

WIMF is currently available as a source-only library. To install the developer suite:

1. Clone the repository:
   ```bash
   git clone https://github.com/benchware/wimf.git
   cd wimf
   ```

2. Install dependencies:
   ```bash
   pip install numpy pillow
   ```

3. Install in editable mode:
   ```bash
   pip install -e .
   ```

*(PyPI release coming soon)*

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

## TODO List

- ~~Finish C++ porting~~ (Core engine complete)
- Mainly use C++ (Porting remaining high-level logic)
- Pure Python Parity (Fallback for all C++ functions)
- Web support
- Test on ARM
- Publish on PyPI
- Mainly use C++

## License
Worst IMage Format is licensed under the GNU General Public License (GPL) v3.0. You are free to use, modify, and distribute this software under the terms of the GPL v3.0.

For more information, see GNU General Public License.
