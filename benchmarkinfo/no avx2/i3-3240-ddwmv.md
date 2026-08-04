# WIMF Benchmark Report — Intel Core i3-3240 (2012 Desktop)

**Date**: 2026-08-04  
**Test System**: Custom PC (ASUS P8H61-MX R2.0)  
**CPU**: Intel Core i3-3240 @ 3.40 GHz (2 cores, 4 threads, Ivy Bridge, 2012)  
**RAM**: 16 GB DDR3-1600 (dual-channel)  
**GPU**: NVIDIA GeForce 9500 GT (not used by WIMF)  
**OS**: Microsoft Windows 11 Pro 24H2 (Build 26100.8875)  
**Python**: 3.14.6  
**WIMF Version**: 2.1  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 4  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  

**Note**: This system was released in 2012 — 14 years old at the time of testing. It runs Windows 11 24H2 through unsupported hardware workarounds. The fact it runs at all is a minor miracle.

---

## Overview

These benchmarks measure the current state of the WIMF encoder on a 14-year-old desktop CPU with DDR3-1600 memory. All numbers were collected with the published PyPI wheel (no local compiler involved). The SIMD path was reported as `scalar`; no platform-specific vector extensions were used. RAM was not a limiting factor in any test.

---

## Fast preset – speed-first encoding

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 41.4      | 3.22×             | 16.08      | 12.93      | 2.8               | 67.6      |
| Q9      | 40.7      | 3.27×             | 12.73      | 7.90       | 3.6               | 62.8      |
| Q8      | 40.3      | 3.30×             | 12.07      | 6.25       | 3.8               | 59.8      |
| Q7      | 40.0      | 3.33×             | 10.07      | 6.36       | 4.5               | 57.6      |
| Q6      | 39.8      | 3.34×             | 9.15       | 4.85       | 5.0               | 55.9      |
| Q5      | 39.6      | 3.36×             | 8.01       | 4.20       | 5.7               | 54.5      |
| Q4      | 39.5      | 3.37×             | 7.64       | 3.73       | 5.9               | 53.4      |
| Q3      | 39.4      | 3.38×             | 7.04       | 3.44       | 6.5               | 52.5      |
| Q2      | 39.3      | 3.39×             | 8.02       | 3.49       | 5.7               | 51.7      |
| Q1      | 39.2      | 3.40×             | **6.50**   | 2.93       | **7.0**           | 51.1      |

**Observations**:
- Peak encode throughput: **7.0 MP/s** (Q1 Fast).
- All Fast runs complete in under 17 seconds.
- This is a 14-year-old desktop with DDR3-1600. **7 MP/s is usable.**
- PSNR ranges from 51.1 dB (Q1) to 67.6 dB (Q10).

---

## Balanced preset – default quality/speed trade-off

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 26.0      | 5.12×             | 24.99      | 3.92       | 1.8               | ∞         |
| Q9      | 26.0      | 5.12×             | 17.81      | 4.09       | 2.6               | **75.8**  |
| Q8      | 25.9      | 5.13×             | 16.72      | 5.63       | 2.7               | 62.9      |
| Q7      | 25.7      | 5.17×             | 14.11      | 7.81       | 3.2               | 57.6      |
| Q6      | 25.6      | 5.21×             | 16.16      | 7.62       | 2.8               | 55.9      |
| Q5      | 25.4      | 5.24×             | 14.07      | 6.69       | 3.2               | 54.5      |
| Q4      | 25.3      | 5.26×             | 14.62      | 7.28       | 3.1               | 53.4      |
| Q3      | 25.2      | 5.28×             | 14.89      | 6.88       | 3.1               | 52.5      |
| Q2      | 25.1      | 5.30×             | 12.83      | 5.94       | 3.5               | 51.7      |
| Q1      | 25.6      | 5.21×             | 14.09      | 3.92       | 3.2               | 55.9      |

**Observations**:
- Throughput is stable at **~3.2 MP/s** across most qualities.
- Q9 Balanced delivers **75.8 dB PSNR** with a 5.12× compression ratio.
- This preset is usable for daily use on old hardware.

---

## Extreme preset – maximum compression

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 24.2      | 5.50×             | 334.39     | 3.59       | 0.1               | ∞         |
| Q9      | 23.0      | 5.79×             | 320.08     | 120.39     | 0.1               | 51.0      |
| Q8      | 18.4      | 7.23×             | 243.61     | 174.79     | 0.2               | 46.5      |
| Q7      | 15.3      | 8.72×             | 250.46     | 213.35     | 0.2               | 44.4      |
| Q6      | 13.0      | 10.22×            | 212.08     | 130.20     | 0.2               | 42.7      |
| Q5      | 11.3      | 11.80×            | 187.49     | 77.18      | 0.2               | 41.4      |
| Q4      | 9.8       | 13.52×            | 127.95     | 69.94      | 0.4               | 40.3      |
| Q3      | 8.7       | 15.36×            | 110.75     | 58.99      | 0.4               | 39.4      |
| Q2      | **7.7**   | **17.31×**        | **100.94** | 52.63      | **0.5**           | 38.7      |
| Q1      | 19.3      | 6.89×             | 97.72      | 10.22      | 0.5               | 45.8      |

**Observations**:
- Best compression: **17.31×** at Q2 (7.7 MB) in **100.9 seconds**.
- Peak throughput on Extreme: **0.5 MP/s**.
- Encode times range from 97 to 334 seconds — **painful but usable for archival**.

---

## Codec‑specific comparison (Q5, all presets)

| Codec      | Preset    | Size (MB) | Compression ratio | Encode (s) | Throughput (MP/s) | PSNR (dB) |
|------------|-----------|----------:|------------------:|-----------:|------------------:|----------:|
| Wavelet    | Balanced  | 13.5      | 9.88×             | 103.06     | 0.4               | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31×             | 115.01     | 0.4               | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×            | 177.80     | 0.3               | 41.4      |
| Predictive | Fast      | 24.6      | 5.41×             | 5.58       | 8.1               | ∞         |
| Predictive | Balanced  | 26.1      | 5.10×             | 6.26       | 7.3               | ∞         |
| Predictive | Extreme   | 24.2      | 5.50×             | 13.73      | 3.3               | ∞         |
| Auto       | Fast      | 39.6      | 3.36×             | 8.01       | 5.7               | 54.5      |
| Auto       | Balanced  | 25.4      | 5.24×             | 14.07      | 3.2               | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×            | 187.49     | 0.2               | 41.4      |
| Palette    | Fast      | 44.6      | 2.98×             | 4.15       | **10.9**          | ∞         |
| Palette    | Balanced  | 44.3      | 3.00×             | 4.15       | 10.9              | ∞         |
| Palette    | Extreme   | 44.1      | 3.02×             | 6.16       | 7.4               | ∞         |
| Raw        | Any       | 133.2     | 1.00×             | ~5.40      | ~8.4              | ∞         |

**Observations**:
- **Palette Fast** is the fastest configuration: **10.9 MP/s**, 44.6 MB — suitable for flat graphics.
- **Auto Fast** is the best practical configuration: **5.7 MP/s**, 39.6 MB.
- **Wavelet Balanced** is the best size/quality balance: 13.5 MB, 103.06 s.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31× ratio  |
| **Fastest encode**    | Palette Fast                | 10.9 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.5 MB, 0.4 MP/s     |
| **Best quality**      | Q9 Balanced                 | 75.8 dB PSNR          |
| **Lossless smallest** | Predictive Fast             | 24.6 MB, 5.41× ratio  |

---

## Hardware context

| **Component** | **Details** |
|---------------|-------------|
| **CPU** | Intel Core i3-3240 @ 3.40 GHz (Ivy Bridge, 2012) |
| **Cores/Threads** | 2 cores, 4 threads |
| **TDP** | 55W |
| **RAM** | 16 GB DDR3-1600 (dual-channel) |
| **Motherboard** | ASUS P8H61-MX R2.0 |
| **OS** | Windows 11 Pro 24H2 (unsupported hardware) |
| **Age at test** | 14 years |

---

## Efficiency comparison

| **System** | **CPU** | **TDP** | **Fast (MP/s)** | **Efficiency (MP/s per W)** |
|------------|---------|---------|-----------------|----------------------------|
| i5-8400 | i5-8400 | 65W | 44.6 | 0.69 |
| i5-4460 | i5-4460 | 84W | 26.7 | 0.32 |
| i3-7100T | i3-7100T | 35W | 22.6 | 0.65 |
| i5-3230M | i5-3230M | 35W | 15.1 | 0.43 |
| i3-7100U | i3-7100U | 15W | 13.1 | **0.87** 🏆 |
| **i3-3240** | **i3-3240** | **55W** | **7.0** | **0.13** |

---

## Known constraints

- All tests were run with **scalar** code paths. The test CPU does not support AVX2.
- This is a 14-year-old desktop with DDR3-1600. Performance is **usable for basic tasks**.
- File sizes are still being tuned. The encoder produces correct output, but the compression search logic is not yet fully optimized for all images.
- **Windows 11 24H2** running on unsupported hardware is a testament to the user's persistence.

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
