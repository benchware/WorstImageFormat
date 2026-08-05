# WIMF Benchmark Report — HP ProBook 640 G3 (Intel Core i5-7200U)

**Date**: 2026-08-05  
**Test System**: HP ProBook 640 G3 (Business Laptop, 2016)  
**CPU**: Intel Core i5-7200U @ 2.50 GHz (2 cores, 4 threads, Kaby Lake, 2016)  
**RAM**: 16 GB DDR4 (dual-channel)  
**Storage**: SSD  
**GPU**: Intel HD Graphics 620 (not used by WIMF)  
**OS**: Microsoft Windows 10 Pro 22H2 (Build 19045)  
**Python**: 3.14.6  
**WIMF Version**: 2.2  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 4  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  
**Measurement methodology**: Each configuration was encoded and decoded five times; the reported values are the median of the three middle runs.

**Note**: This system represents a typical business laptop from 2016 with a 15W TDP Kaby Lake CPU. It runs Windows 10 22H2 with 16 GB of DDR4 memory.

---

## Overview

These benchmarks measure the current state of the WIMF encoder on a 15W Kaby Lake laptop CPU from 2016. All numbers were collected with the published PyPI wheel (no local compiler involved). The SIMD path was reported as `scalar`; no platform-specific vector extensions were used.

The i5-7200U achieves **20.1 MP/s** on Fast preset, outperforming the i3-7100U by 53% despite both being 15W Kaby Lake parts. This is likely due to the higher boost clock (3.1 GHz vs 3.0 GHz).

---

## Fast preset – speed-first encoding

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 41.4      | 3.22×             | 2.70       | 0.70       | 16.8              | 67.6      |
| Q9      | 40.7      | 3.27×             | 2.71       | 0.80       | 16.8              | 62.8      |
| Q8      | 40.3      | 3.30×             | 2.68       | 0.77       | 16.9              | 59.8      |
| Q7      | 40.0      | 3.33×             | 2.30       | 0.72       | 19.8              | 57.6      |
| Q6      | 39.8      | 3.34×             | 2.71       | 0.72       | 16.8              | 55.9      |
| Q5      | 39.6      | 3.36×             | 2.14       | 0.64       | 21.3              | 54.5      |
| Q4      | 39.5      | 3.37×             | 2.18       | 0.61       | 20.8              | 53.4      |
| Q3      | 39.4      | 3.38×             | 2.09       | 0.62       | 21.7              | 52.5      |
| Q2      | 39.3      | 3.39×             | 2.06       | 0.60       | 22.1              | 51.7      |
| Q1      | 39.2      | 3.40×             | 2.26       | 0.78       | 20.1              | 51.1      |

**Observations**:
- Peak encode throughput: **22.1 MP/s** (Q2 Fast).
- All Fast runs complete in under 2.8 seconds.
- PSNR ranges from 51.1 dB (Q1) to 67.6 dB (Q10), with diminishing returns beyond Q7.

---

## Balanced preset – default quality/speed trade-off

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 26.1      | 5.11×             | 6.78       | 1.36       | 6.7               | ∞         |
| Q9      | 26.1      | 5.11×             | 5.97       | 1.43       | 7.6               | **76.4**  |
| Q8      | 26.0      | 5.12×             | 6.18       | 1.73       | 7.4               | 63.2      |
| Q7      | 25.8      | 5.16×             | 7.02       | 1.72       | 6.5               | 57.9      |
| Q6      | 25.6      | 5.20×             | 7.68       | 1.98       | 5.9               | 55.9      |
| Q5      | 25.5      | 5.23×             | 6.97       | 1.59       | 6.5               | 54.5      |
| Q4      | 25.4      | 5.25×             | 6.38       | 1.62       | 7.1               | 53.4      |
| Q3      | 25.3      | 5.27×             | 7.23       | 1.98       | 6.3               | 52.5      |
| Q2      | 25.2      | 5.29×             | 7.11       | 1.68       | 6.4               | 51.7      |
| Q1      | 25.6      | 5.20×             | 6.95       | 1.71       | 6.5               | 56.0      |

**Observations**:
- Throughput is stable at **~6.5 MP/s** across most qualities.
- Q9 Balanced delivers **76.4 dB PSNR** with a 5.11× compression ratio — visually lossless for most content.
- This preset is the recommended default for daily use.

---

## Extreme preset – maximum compression

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 24.2      | 5.50×             | 49.57      | 1.59       | 0.9               | ∞         |
| Q9      | 23.0      | 5.79×             | 36.26      | 3.53       | 1.3               | 51.0      |
| Q8      | 18.4      | 7.23×             | 32.73      | 3.97       | 1.4               | 46.5      |
| Q7      | 15.3      | 8.72×             | 30.17      | 3.82       | 1.5               | 44.4      |
| Q6      | 13.0      | 10.22×            | 27.88      | 3.73       | 1.6               | 42.7      |
| Q5      | 11.3      | 11.80×            | 26.66      | 3.93       | 1.7               | 41.4      |
| Q4      | 9.8       | 13.52×            | 26.48      | 3.89       | 1.7               | 40.3      |
| Q3      | 8.7       | 15.36×            | 25.72      | 3.99       | 1.8               | 39.4      |
| Q2      | **7.7**   | **17.31×**        | **27.10**  | 4.58       | **1.7**           | 38.7      |
| Q1      | 19.3      | 6.89×             | 30.42      | 2.68       | 1.5               | 45.8      |

**Observations**:
- Best compression: **17.31×** at Q2 (7.7 MB) in **27.10 seconds**.
- Peak throughput on Extreme: **1.8 MP/s**.
- Encode times range from 25.7 to 49.6 seconds.

---

## Codec‑specific comparison (Q5, all presets)

| Codec      | Preset    | Size (MB) | Compression ratio | Encode (s) | Throughput (MP/s) | PSNR (dB) |
|------------|-----------|----------:|------------------:|-----------:|------------------:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72×             | 8.92       | **5.1**           | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31×             | 8.57       | 5.3               | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×            | 15.61      | 2.9               | 41.4      |
| Predictive | Fast      | 24.6      | 5.41×             | 4.21       | 10.8              | ∞         |
| Predictive | Balanced  | 26.1      | 5.09×             | 4.41       | 10.3              | ∞         |
| Predictive | Extreme   | 24.2      | 5.50×             | 9.82       | 4.6               | ∞         |
| Auto       | Fast      | 39.6      | 3.36×             | 2.14       | 21.3              | 54.5      |
| Auto       | Balanced  | 25.5      | 5.23×             | 6.97       | 6.5               | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×            | 26.66      | 1.7               | 41.4      |
| Palette    | Fast      | 44.6      | 2.98×             | 1.89       | **24.0**          | ∞         |
| Palette    | Balanced  | 44.4      | 3.00×             | 2.01       | 22.6              | ∞         |
| Palette    | Extreme   | 44.1      | 3.02×             | 3.46       | 13.1              | ∞         |
| Raw        | Any       | 133.2     | 1.00×             | ~2.39      | ~19.0             | ∞         |

**Observations**:
- **Palette Fast** is the fastest configuration: **24.0 MP/s**, 44.6 MB — suitable for flat graphics.
- **Wavelet Balanced** is the best balance of size, speed, and quality: 13.7 MB, 8.92 s, 41.4 dB.
- **Auto Fast** delivers 21.3 MP/s with 54.5 dB PSNR.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31× ratio  |
| **Fastest encode**    | Palette Fast                | 24.0 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 5.1 MP/s     |
| **Best quality**      | Q9 Balanced                 | 76.4 dB PSNR          |
| **Lossless smallest** | Predictive Fast             | 24.6 MB, 5.41× ratio  |

---

## Hardware context

| **Component** | **Details** |
|---------------|-------------|
| **CPU** | Intel Core i5-7200U @ 2.50 GHz (Kaby Lake, 2016) |
| **Cores/Threads** | 2 cores, 4 threads |
| **TDP** | 15W |
| **RAM** | 16 GB DDR4 (dual-channel) |
| **Storage** | SSD |
| **OS** | Windows 10 Pro 22H2 (Build 19045) |
| **Python** | 3.14.6 |

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
