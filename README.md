<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/white.png">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/dark.png">
    <img alt="Worst Image Format" src="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/dark.png" width="500">
  </picture>
</p>

# WIMF — Worst IMage Format

[![PyPI](https://img.shields.io/pypi/v/wimf.svg)](https://pypi.org/project/wimf/)
[![Python](https://img.shields.io/pypi/pyversions/wimf.svg)](https://pypi.org/project/wimf/)
[![CI](https://github.com/benchware/WorstImageFormat/actions/workflows/ci.yml/badge.svg)](https://github.com/benchware/WorstImageFormat/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/wimf.svg)](https://github.com/benchware/WorstImageFormat/blob/main/LICENSE)

WIMF is an experimental, versioned image codec with a Python frontend and a portable C++17 backend. New still images use the WIM2 hybrid container: every 128×128 tile independently chooses Raw, Predictive, Palette, or CDF Wavelet coding and records its mode, entropy backend, bounds, size, offset, and checksum.

WIMF 2.0 is available on [PyPI](https://pypi.org/project/wimf/). WIM2 still-image coding, ROI decoding, high bit depth, native kernels, optional anti-rot recovery, and indexed chrono history are implemented. Legacy WIMF/AWIF decoding remains available; animation and coefficient watermark creation still use v1.

## Highlights

- Per-tile hybrid selection with `Fast`, `Balanced`, and `Extreme` search presets.
- Exact lossless coding and quality-controlled CDF 9/7 lossy wavelets.
- Palette coding for local regions with at most 256 colors.
- Spatial prediction with row-level predictor selection.
- Independently decodable tiles for bounded ROI reads.
- RGB, RGBA, grayscale, and 8/10/16-bit pixel pipelines.
- Zstandard-compressed structured symbols and per-tile CRC32 checksums.
- Optional WIM2 anti-rot data capable of repairing up to two damaged shards.
- Indexed WIM2 chrono states with random state decoding.
- Portable C++17 kernels with a Python reference fallback.

## Installation

Install the published package with Python 3.10 or newer:

```bash
python -m pip install wimf
```

Precompiled wheels are published for Linux x86-64, Windows x86-64, macOS Intel, and macOS Apple Silicon across CPython 3.10–3.14. A matching wheel does not require a local compiler.

For development:

```bash
git clone https://github.com/benchware/WorstImageFormat.git
cd WorstImageFormat
python -m pip install -e .
```

Source installations require a C++17 compiler and pybind11; the Python fallback remains usable when the native extension is unavailable.

## Python API

```python
from PIL import Image
import wimf

image = Image.open("photo.png")

# Balanced per-tile selection is the default.
output = wimf.save("photo.wimf", image, quality=7)

# Exact reconstruction and explicit legacy output.
wimf.save("exact.wimf", image, lossless=True)
wimf.save("legacy.wimf", image, lossless=True, format_version=1)

decoded = wimf.open("photo.wimf")
decoded.pil.save("decoded.png")

# Memory-only applications can use bytes directly.
payload = wimf.encode(image, lossless=True, metadata={"author": "Bee"})
decoded = wimf.decode(payload)
details = wimf.inspect(payload)
```

`codec` accepts `auto`, `wavelet`, `predictive`, `palette`, or `raw`. `preset` accepts `Fast`, `Balanced`, or `Extreme`.

### ROI decoding

```python
decoder = wimf.WIMFDecoder("large.wimf")
region = decoder.decode(roi=(1024, 768, 640, 480))
```

Only intersecting WIM2 tile payloads are decompressed.

### Anti-rot and chrono history

```python
encoder = wimf.WIMFEncoder(image).set_anti_rot()
encoder.add_chrono_state(edited_image)
payload = encoder.encode(lossless=True)

decoder = wimf.WIMFDecoder(payload)
original = decoder.decode_chrono_state(0)
edited = decoder.decode_chrono_state(1)
print(decoder.was_protected, decoder.was_repaired)
```

WIM2 extensions are appended after the base tile payload. Existing WIM2 files remain valid and older readers can still decode the primary image.

### Runtime diagnostics

```python
print(wimf.runtime_info())
```

The result reports whether native kernels are active, architecture, SIMD path, hardware and effective thread counts, codec version, and Zstandard version.

### Mandelbrot example

The included generator renders a Mandelbrot set with NumPy and writes WIMF directly:

```bash
python examples/mandelbrot_wimf.py mandelbrot.wimf --width 1920 --height 1080 --quality 7
```

Use `--lossless`, force a tile mode with `--codec`, or zoom using `--center-x`, `--center-y`, and `--span`.

## Command-line tools

The unified command covers the normal workflow:

```bash
wimf encode photo.png photo.wimf --quality 7
wimf encode artwork.png artwork.wimf --lossless
wimf decode photo.wimf photo.png
wimf decode huge.wimf crop.png --roi 100 200 640 480
wimf info photo.wimf
wimf runtime
wimf view photo.wimf
wimf base64 encode photo.wimf photo.txt --data-url
wimf corrupt photo.wimf damaged.wimf --seed 42 --area payload
wimf diagnose damaged.wimf --unsafe-preview damaged-preview.png
```

Run `wimf <command> --help` for focused options. Metadata uses repeatable `--metadata KEY=VALUE` arguments. The original specialized commands remain available:

- `wimf-convert` provides legacy conversion, animation, depth-map, and watermark flags.
- AWIF animation preserves GIF frame durations, average FPS, and loop count; legacy files without timing metadata use the historical 30 FPS default. See the [AWIF compatibility and CI matrix](docs/awif-testing.md).
- `wimf-studio` opens the encoder, comparison viewer, tile inspector, protection/history tools, and codec lab.
- `wimf-view` is a compatibility alias that opens WIMF Studio.
- `wimf-cat` renders supported images in compatible terminals.
- `wimf-meta` inspects and edits legacy metadata.

### WIMF Studio and corruption experiments

WIMF Studio uses four focused panels: Encode & Compare, Inspect, Protection & History, and Codec Lab. Long-running encoding runs outside the Tk event loop and native tile progress can be cancelled between tiles.

The Codec Lab never disables normal checksum validation. Its unsafe preview decodes only checksum-valid independent tiles and replaces rejected tiles with an obvious checkerboard. Base64 is treated as a transport representation, including `data:image/x-wimf;base64,...` URLs; it is not a new compression mode.

## Compatibility and status

| Capability | WIM2 | Legacy decode |
|---|---|---|
| Hybrid still images | Implemented | WIMF v1 supported |
| Lossless and lossy coding | Implemented | Supported |
| ROI and independent tiles | Implemented | Format-dependent |
| Anti-rot | Two-shard WIM2 extension | `ROT!` supported |
| Chrono history | Indexed WIM2 extension | AWIF states supported |
| Animation creation | Planned | v1 only |
| Wavelet watermark creation | Planned | v1 only |

See the [WIM2 format overview](docs/wim2-format.md), [native embedding guide](docs/native-core.md), and
[release checklist](docs/release-checklist.md) for implementation and publishing details.

## Verification and roadmap

CI runs Python quality checks, native and fallback codec tests, standalone C++ tests on Windows/Linux/macOS, source-distribution validation, and an image-based codec report. The active roadmap is:

- Profile the completed native orchestration and optimize only measured allocation, transform, or entropy-coding hotspots.
- Verify Linux ARM64 and Windows ARM64 wheels on dedicated native runners.
- Expand measured AVX2 and NEON optimization only where profiling justifies it.
- Validate the memory-only synchronous core with Emscripten on the future web branch without changing the WIM2 bitstream.
- Migrate animation and watermark creation only after the still-image path meets throughput targets.

Target performance is at least 10 MP/s Balanced encoding and 50 MP/s decoding on reference hardware; benchmark results are hardware-dependent and are not claimed until measured.

## License

WIMF is licensed under GPL-3.0-or-later.

## Reporting bugs

WIMF is experimental. If something breaks, please [open a GitHub issue](https://github.com/benchware/WorstImageFormat/issues) with your operating system, Python version, `wimf runtime --json` output, and a minimal sample file when possible. WIMF Studio's **Help → Report a Bug** command copies the relevant runtime diagnostics and opens the issue page.
