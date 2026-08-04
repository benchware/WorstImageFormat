# WIMF Benchmark Report — HP ProDesk 600 G3 (Core i3-7100T)

**Date**: 2026-08-04  
**Test System**: HP ProDesk 600 G3 DM (Mini Desktop, 2017)  
**CPU**: Intel Core i3-7100T @ 3.40 GHz (2 cores, 4 threads, Kaby Lake, 2017)  
**RAM**: 16 GB DDR4-2400 (dual-channel, Micron + Samsung)  
**Storage**: 256 GB NVME SSD (btrfs) + 1 TB HDD (ext4)  
**GPU**: Intel HD Graphics 630 (not used by WIMF)  
**OS**: CachyOS (Arch-based Linux, 7.1.3-2-cachyos)  
**Python**: 3.14.6  
**WIMF Version**: 2.2  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 4  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  

**Note**: This system represents a typical business desktop form factor with a low-power 35W Kaby Lake CPU running a performance-optimized Linux distribution.

---

## Overview

These benchmarks measure the current state of the WIMF encoder on a 35W Kaby Lake desktop CPU from 2017. The system runs CachyOS, an Arch-based Linux distribution optimized for performance. The SIMD path was reported as `scalar`; no platform-specific vector extensions were used.

---

## Fast preset – speed-first encoding

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 41.4      | 3.22×             | 2.50       | 0.66       | 18.2              | 67.6      |
| Q9      | 40.7      | 3.27×             | 2.89       | 0.42       | 15.7              | 62.8      |
| Q8      | 40.3      | 3.30×             | 2.17       | 0.38       | 21.0              | 59.8      |
| Q7      | 40.0      | 3.33×             | 2.14       | 0.38       | 21.2              | 57.6      |
| Q6      | 39.8      | 3.34×             | 2.17       | 0.38       | 20.9              | 55.9      |
| Q5      | 39.6      | 3.36×             | 2.12       | 0.36       | 21.4              | 54.5      |
| Q4      | 39.5      | 3.37×             | 2.15       | 0.37       | 21.2              | 53.4      |
| Q3      | 39.4      | 3.38×             | 2.14       | 0.36       | 21.2              | 52.5      |
| Q2      | 39.3      | 3.39×             | 2.17       | 0.38       | 21.0              | 51.7      |
| Q1      | 39.2      | 3.40×             | 2.11       | 0.35       | 21.5              | 51.1      |

**Observations**:
- Peak encode throughput: **21.5 MP/s** (Q1 Fast).
- All Fast runs complete in under 2.9 seconds.
- PSNR ranges from 51.1 dB (Q1) to 67.6 dB (Q10), with diminishing returns beyond Q7.

---

## Balanced preset – default quality/speed trade-off

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 26.1      | 5.11×             | 4.53       | 0.78       | 10.0              | ∞         |
| Q9      | 26.1      | 5.11×             | 4.47       | 0.78       | 10.2              | **76.4**  |
| Q8      | 26.0      | 5.12×             | 4.47       | 0.80       | 10.2              | 63.2      |
| Q7      | 25.8      | 5.16×             | 4.42       | 0.80       | 10.3              | 57.9      |
| Q6      | 25.6      | 5.20×             | 4.55       | 0.81       | 10.0              | 55.9      |
| Q5      | 25.5      | 5.23×             | 4.51       | 0.80       | 10.1              | 54.5      |
| Q4      | 25.4      | 5.25×             | 4.67       | 0.81       | 9.7               | 53.4      |
| Q3      | 25.3      | 5.27×             | 4.44       | 0.79       | 10.2              | 52.5      |
| Q2      | 25.2      | 5.29×             | 4.41       | 0.81       | 10.3              | 51.7      |
| Q1      | 25.6      | 5.20×             | 4.42       | 0.79       | 10.3              | 56.0      |

**Observations**:
- Throughput is stable at **~10.2 MP/s** across all qualities.
- Q9 Balanced delivers **76.4 dB PSNR** with a 5.11× compression ratio — visually lossless for most content.
- This preset is the recommended default for daily use.

---

## Extreme preset – maximum compression

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 24.2      | 5.50×             | 26.96      | 0.78       | 1.7               | ∞         |
| Q9      | 23.0      | 5.79×             | 24.00      | 1.41       | 1.9               | 51.0      |
| Q8      | 18.4      | 7.23×             | 21.51      | 1.59       | 2.1               | 46.5      |
| Q7      | 15.3      | 8.72×             | 19.75      | 1.52       | 2.3               | 44.4      |
| Q6      | 13.0      | 10.22×            | 18.49      | 1.47       | 2.5               | 42.7      |
| Q5      | 11.3      | 11.80×            | 17.09      | 1.44       | 2.7               | 41.4      |
| Q4      | 9.8       | 13.52×            | 16.15      | 1.42       | 2.8               | 40.3      |
| Q3      | 8.7       | 15.36×            | 15.36      | 1.40       | 3.0               | 39.4      |
| Q2      | **7.7**   | **17.31×**        | **14.81**  | 1.39       | **3.1**           | 38.7      |
| Q1      | 19.3      | 6.89×             | 14.56      | 0.96       | 3.1               | 45.8      |

**Observations**:
- Best compression: **17.31×** at Q2 (7.7 MB) in **14.81 seconds**.
- Peak throughput on Extreme: **3.1 MP/s**.
- Encode times range from 14.6 to 27.0 seconds.

---

## Codec‑specific comparison (Q5, all presets)

| Codec      | Preset    | Size (MB) | Compression ratio | Encode (s) | Throughput (MP/s) | PSNR (dB) |
|------------|-----------|----------:|------------------:|-----------:|------------------:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72×             | 3.33       | **13.7**          | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31×             | 3.00       | 15.1              | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×            | 8.37       | 5.4               | 41.4      |
| Predictive | Fast      | 24.6      | 5.41×             | 2.16       | 21.0              | ∞         |
| Predictive | Balanced  | 26.1      | 5.09×             | 2.66       | 17.1              | ∞         |
| Predictive | Extreme   | 24.2      | 5.50×             | 6.76       | 6.7               | ∞         |
| Auto       | Fast      | 39.6      | 3.36×             | 2.12       | 21.4              | 54.5      |
| Auto       | Balanced  | 25.5      | 5.23×             | 4.51       | 10.1              | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×            | 17.09      | 2.7               | 41.4      |
| Palette    | Fast      | 44.6      | 2.98×             | 1.73       | **26.3**          | ∞         |
| Palette    | Balanced  | 44.4      | 3.00×             | 1.98       | 22.9              | ∞         |
| Palette    | Extreme   | 44.1      | 3.02×             | 2.89       | 15.7              | ∞         |
| Raw        | Any       | 133.2     | 1.00×             | ~1.66      | ~27.4             | ∞         |

**Observations**:
- **Palette Fast** is the fastest configuration: **26.3 MP/s**.
- **Wavelet Balanced** is the best balance of size, speed, and quality: 13.7 MB, 3.33 s, 41.4 dB.
- **Auto Fast** delivers 21.4 MP/s with 54.5 dB PSNR.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31× ratio  |
| **Fastest encode**    | Palette Fast                | 26.3 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 13.7 MP/s    |
| **Best quality**      | Q9 Balanced                 | 76.4 dB PSNR          |
| **Lossless smallest** | Predictive Fast             | 24.6 MB, 5.41× ratio  |

---

## Hardware context

| **Component** | **Details** |
|---------------|-------------|
| **CPU** | Intel Core i3-7100T @ 3.40 GHz (Kaby Lake, 2017) |
| **Cores/Threads** | 2 cores, 4 threads |
| **TDP** | 35W |
| **RAM** | 16 GB DDR4-2400 (dual-channel) |
| **RAM Modules** | Micron + Samsung |
| **Storage** | 256 GB NVME SSD (btrfs) + 1 TB HDD |
| **OS** | CachyOS (Arch-based Linux) |
| **Kernel** | Linux 7.1.3-2-cachyos |

---

## Known constraints

- All tests were run with **scalar** code paths. The test CPU does not support AVX2.
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
