<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/white.png">
    <source media="(prefers-color-scheme: light)" srcset=".github/assets/dark.png">
    <img alt="Worst Image Format Logo" src=".github/assets/dark.png" width="500">
  </picture>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3">
  <img src="https://img.shields.io/badge/python-3.10+-aff.svg" alt="Python: 3.10+">
  <img src="https://img.shields.io/badge/format-.wimf%20%7C%20.wif-orange" alt="Format: .wimf | .wif">
  <img src="https://img.shields.io/badge/RMSE-Fixed-green" alt="RMSE Score: Fixed">
</p>

This project is just a fancy image format that absolutely seems to have no use... (for now)
> Note: This is CLI-only! You could use the web port by *ddwmv* (contributor)
## Features

- **Progressive Loading**: Chunked Bitstream structure allows for the low resolution image to improve gradually as the file loads.
- **HDR10 Support**: Full support for HDR data and light level metadata (MaxCLL/MaxFALL)
- Full **Alpha Channel** support.
- Native support for 5-channel data (RGBA + Depth) for 3D and AR applications.

You might be wondering, how does the codec work? Well, let me show you how it functions behind the scenes:
- **Haar Wavelet Engine**: Multi-level frequency decomposition, it prioritizes image structure over noise. Fails with painterly blurs instead of JPG blocks.
- **Reversible YCoCg-R**: A high-efficiency color transform that provides better decorrelation and color accuracy than standard YCbCr.
- **Variable Bit-Depth**: Fully supports 8-bit, 10-bit, and 16-bit precision pipelines.
- **Compression**: Lossless utilizes bit-exact reconstruction via Paeth prediction algorithm. On the other hand, Lossy utilizes quantization based compression with adaptive thresholding.
- **LZMA Entropy Coding**: Deep dictionary based compression for maximum data density.

## Developer Tools
- **wimf Python Library**: Easy-to-use API for loading and saving images.
- **CLI Converter (`wimf-convert`)**: Command-line tool for batch conversion and format migration (supports PNG, JPEG, GIF).
- **Image Viewer (`wimf-view`)**: High-performance player with progressive loading and real-time animation playback.
- **GUI Suite (`wimf-gui`)**: Graphical frontend for all codec features and metadata management.
- **Metadata Engine**: Automatic EXIF extraction and preservation from source files.

## Format Specification
License: GPL 3.0
