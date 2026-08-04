# WIMF Benchmark Report — AMD Ryzen 3 7320U (Vivobook Go E1404FA)

**Date**: 2026-08-04  
**Test System**: ASUS Vivobook Go E1404FA (Laptop)  
**CPU**: AMD Ryzen 3 7320U @ 2.40 GHz (4 cores, 8 threads, Zen 2, 2023)  
**RAM**: 8 GB LPDDR5-5500 (2×4 GB, dual-channel)  
**Storage**: 512 GB NVMe SSD (Samsung)  
**GPU**: AMD Radeon 610M (not used by WIMF)  
**OS**: CachyOS (Linux 7.1.5-1-cachyos)  
**DE**: Hyprland (Wayland compositor)  
**Python**: 3.14.6  
**WIMF Version**: 2.2  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 8  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  
**Measurement methodology**: Each configuration was encoded and decoded five times; the reported values are the median of the three middle runs.

**Note**: This system represents a modern budget laptop with a Zen 2-based APU, LPDDR5 memory, and a fast NVMe SSD. The benchmark was run in a TTY session to eliminate GUI overhead.

---

## Overview

These benchmarks measure the current state of the WIMF encoder on a modern Zen 2-based APU from 2023. The system runs CachyOS, an Arch-based Linux distribution optimized for performance. The SIMD path was reported as `scalar`; no platform-specific vector extensions were used.

The Ryzen 3 7320U achieves the highest performance of any system tested so far, reaching **45.2 MP/s** on Fast preset. This is likely due to the combination of 8 threads, efficient Zen 2 cores, LPDDR5 memory, and the optimized CachyOS kernel.

---

## Fast preset – speed-first encoding

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 41.4      | 3.22×             | 1.30       | 0.23       | 34.9              | 67.6      |
| Q9      | 40.7      | 3.27×             | 1.18       | 0.24       | 38.4              | 62.8      |
| Q8      | 40.3      | 3.30×             | 1.17       | 0.21       | 38.7              | 59.8      |
| Q7      | 40.0      | 3.33×             | 1.17       | 0.22       | 38.8              | 57.6      |
| Q6      | 39.8      | 3.34×             | 1.16       | 0.21       | 39.1              | 55.9      |
| Q5      | 39.6      | 3.36×             | 1.16       | 0.22       | 39.0              | 54.5      |
| Q4      | 39.5      | 3.37×             | 1.16       | 0.21       | 39.3              | 53.4      |
| Q3      | 39.4      | 3.38×             | 1.16       | 0.22       | 39.2              | 52.5      |
| Q2      | 39.3      | 3.39×             | 1.15       | 0.21       | 39.5              | 51.7      |
| Q1      | 39.2      | 3.40×             | 1.20       | 0.22       | 38.0              | 51.1      |

**Observations**:
- Peak encode throughput: **39.5 MP/s** (Q2 Fast).
- All Fast runs complete in under 1.3 seconds.
- PSNR ranges from 51.1 dB (Q1) to 67.6 dB (Q10), with diminishing returns beyond Q7.

---

## Balanced preset – default quality/speed trade-off

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 26.1      | 5.11×             | 2.03       | 0.36       | 22.4              | ∞         |
| Q9      | 26.1      | 5.11×             | 2.04       | 0.37       | 22.3              | **76.4**  |
| Q8      | 26.0      | 5.12×             | 2.01       | 0.37       | 22.6              | 63.2      |
| Q7      | 25.8      | 5.16×             | 2.01       | 0.37       | 22.6              | 57.9      |
| Q6      | 25.6      | 5.20×             | 1.996      | 0.37       | 22.8              | 55.9      |
| Q5      | 25.5      | 5.23×             | 1.999      | 0.37       | 22.7              | 54.5      |
| Q4      | 25.4      | 5.25×             | 1.998      | 0.37       | 22.7              | 53.4      |
| Q3      | 25.3      | 5.27×             | 1.998      | 0.37       | 22.7              | 52.5      |
| Q2      | 25.2      | 5.29×             | 1.984      | 0.37       | 22.9              | 51.7      |
| Q1      | 25.6      | 5.20×             | 2.002      | 0.37       | 22.7              | 56.0      |

**Observations**:
- Throughput is stable at **~22.7 MP/s** across all qualities.
- Q9 Balanced delivers **76.4 dB PSNR** with a 5.11× compression ratio — visually lossless for most content.
- This preset is the recommended default for daily use.

---

## Extreme preset – maximum compression

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 24.2      | 5.50×             | 11.29      | 0.36       | 4.0               | ∞         |
| Q9      | 23.0      | 5.79×             | 10.02      | 0.59       | 4.5               | 51.0      |
| Q8      | 18.4      | 7.23×             | 8.94       | 0.65       | 5.1               | 46.5      |
| Q7      | 15.3      | 8.72×             | 8.20       | 0.63       | 5.5               | 44.4      |
| Q6      | 13.0      | 10.22×            | 7.57       | 0.61       | 6.0               | 42.7      |
| Q5      | 11.3      | 11.80×            | 7.11       | 0.60       | 6.4               | 41.4      |
| Q4      | 9.8       | 13.52×            | 6.72       | 0.59       | 6.8               | 40.3      |
| Q3      | 8.7       | 15.36×            | 6.47       | 0.59       | 7.0               | 39.4      |
| Q2      | **7.7**   | **17.31×**        | **6.22**   | 0.58       | **7.3**           | 38.7      |
| Q1      | 19.3      | 6.89×             | 6.22       | 0.43       | 7.3               | 45.8      |

**Observations**:
- Best compression: **17.31×** at Q2 (7.7 MB) in **6.22 seconds**.
- Peak throughput on Extreme: **7.3 MP/s**.
- Encode times range from 6.2 to 11.3 seconds — **fast enough for archival use**.

---

## Codec‑specific comparison (Q5, all presets)

| Codec      | Preset    | Size (MB) | Compression ratio | Encode (s) | Throughput (MP/s) | PSNR (dB) |
|------------|-----------|----------:|------------------:|-----------:|------------------:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72×             | 1.58       | 28.8              | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31×             | 1.43       | 31.7              | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×            | 3.46       | 13.1              | 41.4      |
| Predictive | Fast      | 24.6      | 5.41×             | 1.19       | 38.3              | ∞         |
| Predictive | Balanced  | 26.1      | 5.09×             | 1.36       | 33.5              | ∞         |
| Predictive | Extreme   | 24.2      | 5.50×             | 3.27       | 13.9              | ∞         |
| Auto       | Fast      | 39.6      | 3.36×             | 1.16       | 39.0              | 54.5      |
| Auto       | Balanced  | 25.5      | 5.23×             | 2.00       | 22.7              | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×            | 7.08       | 6.4               | 41.4      |
| Palette    | Fast      | 44.6      | 2.98×             | **1.01**   | **45.2**          | ∞         |
| Palette    | Balanced  | 44.4      | 3.00×             | 1.11       | 41.0              | ∞         |
| Palette    | Extreme   | 44.1      | 3.02×             | 1.47       | 30.9              | ∞         |
| Raw        | Any       | 133.2     | 1.00×             | ~1.52      | ~29.9             | ∞         |

**Observations**:
- **Palette Fast** is the fastest configuration: **45.2 MP/s**.
- **Wavelet Balanced** is the best balance of size, speed, and quality: 13.7 MB, 1.58 s, 41.4 dB.
- **Auto Fast** delivers 39.0 MP/s with 54.5 dB PSNR.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31× ratio  |
| **Fastest encode**    | Palette Fast                | 45.2 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 28.8 MP/s    |
| **Best quality**      | Q9 Balanced                 | 76.4 dB PSNR          |
| **Lossless smallest** | Predictive Fast             | 24.6 MB, 5.41× ratio  |

---

## Hardware context

| **Component** | **Details** |
|---------------|-------------|
| **CPU** | AMD Ryzen 3 7320U @ 2.40 GHz (Zen 2, 2023) |
| **Cores/Threads** | 4 cores, 8 threads |
| **TDP** | 15W |
| **RAM** | 8 GB LPDDR5-5500 (2×4 GB, dual-channel) |
| **Storage** | 512 GB NVMe SSD (Samsung) |
| **GPU** | AMD Radeon 610M (not used) |
| **OS** | CachyOS (Arch-based Linux) |
| **Kernel** | Linux 7.1.5-1-cachyos |
| **DE** | Hyprland (Wayland) — benchmark run in TTY |

---

## Known constraints

- All tests were run with **scalar** code paths. The test CPU supports AVX2, but the current wheel does not enable it. Preliminary estimates suggest 2.5–3× throughput gains once AVX2 optimizations land.
- File sizes are still being tuned. The encoder produces correct output, but the compression search logic is not yet fully optimized for all images.
- These numbers represent one 45 MP photograph. Real-world performance varies with image content, resolution, and available threads.

---

## Reproducibility

To reproduce these results on your own hardware:

```bash
pip install wimf pillow numpy
python -c "
from PIL import Image
import wimf
import time
import numpy as np

img = Image.open('your_image.jpg')
t0 = time.perf_counter()
wimf.save('test.wimf', img, quality=5, preset='Balanced')
print(f'{(8256*5504/1e6) / (time.perf_counter()-t0):.1f} MP/s')
"
