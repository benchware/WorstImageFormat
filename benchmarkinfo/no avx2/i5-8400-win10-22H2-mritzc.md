# WIMF Benchmark Report — Intel Core i5-8400

**Date**: 2026-08-04  
**Test System**: Intel Core i5-8400 (Coffee Lake, 6 cores, 2017)  
**RAM**: 16 GB DDR4 @ 3200 MHz  
**GPU**: NVIDIA GeForce RTX 2060 (not used by WIMF)  
**Python**: 3.14.6  
**WIMF Version**: 2.2  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 6  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  
**Measurement methodology**: Each configuration was encoded and decoded five times; the reported values are the median of the three middle runs.

---

## Overview

These benchmarks measure the current state of the WIMF encoder on a mainstream 6-core desktop CPU from 2017. All numbers were collected with the published PyPI wheel (no local compiler involved). The SIMD path was reported as `scalar`; no platform-specific vector extensions were used. RAM was not a limiting factor in any test; peak memory usage remained well below available system memory.

---

## Fast preset – speed-first encoding

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 41.4      | 3.22×             | 1.10       | 0.31       | 41.3              | 67.6      |
| Q9      | 40.7      | 3.27×             | 1.17       | 0.32       | 39.0              | 62.8      |
| Q8      | 40.3      | 3.30×             | 1.14       | 0.30       | 39.8              | 59.8      |
| Q7      | 40.0      | 3.33×             | 1.11       | 0.31       | 41.0              | 57.6      |
| Q6      | 39.8      | 3.34×             | 1.11       | 0.30       | 40.9              | 55.9      |
| Q5      | 39.6      | 3.36×             | 1.07       | 0.30       | 42.6              | 54.5      |
| Q4      | 39.5      | 3.37×             | 1.06       | 0.29       | 43.0              | 53.4      |
| Q3      | 39.4      | 3.38×             | 1.08       | 0.29       | 41.9              | 52.5      |
| Q2      | 39.3      | 3.39×             | 1.04       | 0.30       | 43.5              | 51.7      |
| Q1      | 39.2      | 3.40×             | 1.05       | 0.29       | 43.5              | 51.1      |

**Observations**:
- Peak encode throughput: **43.5 MP/s** (Q1 Fast).
- All Fast runs complete in under 1.2 seconds.
- PSNR ranges from 51.1 dB (Q1) to 67.6 dB (Q10), with diminishing returns beyond Q7.

---

## Balanced preset – default quality/speed trade-off

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 26.1      | 5.11×             | 2.11       | 0.50       | 21.5              | ∞         |
| Q9      | 26.1      | 5.11×             | 2.10       | 0.51       | 21.6              | **76.4**  |
| Q8      | 26.0      | 5.12×             | 2.07       | 0.52       | 21.9              | 63.2      |
| Q7      | 25.8      | 5.16×             | 2.05       | 0.54       | 22.2              | 57.9      |
| Q6      | 25.6      | 5.20×             | 2.02       | 0.54       | 22.5              | 55.9      |
| Q5      | 25.5      | 5.23×             | 2.03       | 0.53       | 22.4              | 54.5      |
| Q4      | 25.4      | 5.25×             | 2.03       | 0.53       | 22.4              | 53.4      |
| Q3      | 25.3      | 5.27×             | 2.01       | 0.53       | 22.6              | 52.5      |
| Q2      | 25.2      | 5.29×             | 2.03       | 0.53       | 22.4              | 51.7      |
| Q1      | 25.6      | 5.20×             | 2.02       | 0.52       | 22.4              | 56.0      |

**Observations**:
- Throughput is stable at **~22.4 MP/s** for Q1–Q8.
- Q9 Balanced delivers **76.4 dB PSNR** with a 5.11× compression ratio — visually lossless for most content.
- This preset is the recommended default for daily use.

---

## Extreme preset – maximum compression

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 24.2      | 5.50×             | 17.44      | 0.78       | 2.6               | ∞         |
| Q9      | 23.0      | 5.79×             | 14.45      | 1.14       | 3.1               | 51.0      |
| Q8      | 18.4      | 7.23×             | 12.20      | 1.55       | 3.7               | 46.5      |
| Q7      | 15.3      | 8.72×             | 12.70      | 1.34       | 3.6               | 44.4      |
| Q6      | 13.0      | 10.22×            | 10.50      | 1.44       | 4.3               | 42.7      |
| Q5      | 11.3      | 11.80×            | 10.21      | 1.50       | 4.5               | 41.4      |
| Q4      | 9.8       | 13.52×            | 9.33       | 1.34       | 4.9               | 40.3      |
| Q3      | 8.7       | 15.36×            | 8.82       | 1.33       | 5.2               | 39.4      |
| Q2      | **7.7**   | **17.31×**        | **8.21**   | 1.32       | **5.5**           | 38.7      |
| Q1      | 19.3      | 6.89×             | 8.13       | 0.82       | 5.6               | 45.8      |

**Observations**:
- Best compression: **17.31×** at Q2 (7.7 MB) in **8.21 seconds**.
- Peak throughput on Extreme: **5.5 MP/s** at Q2.
- Encode times range from 8.1 to 17.4 seconds.
- PSNR drops below 40 dB only at Q2; Q3 and above remain above 39 dB.

---

## Codec‑specific comparison (Q5, all presets)

| Codec      | Preset    | Size (MB) | Compression ratio | Encode (s) | Throughput (MP/s) | PSNR (dB) |
|------------|-----------|----------:|------------------:|-----------:|------------------:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72×             | 3.05       | 14.9              | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31×             | 2.83       | 16.1              | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×            | 5.37       | 8.5               | 41.4      |
| Predictive | Fast      | 24.6      | 5.41×             | 1.67       | 27.3              | ∞         |
| Predictive | Balanced  | 26.1      | 5.09×             | 1.80       | 25.2              | ∞         |
| Predictive | Extreme   | 24.2      | 5.50×             | 3.69       | 12.3              | ∞         |
| Auto       | Fast      | 39.6      | 3.36×             | 1.07       | 42.6              | 54.5      |
| Auto       | Balanced  | 25.5      | 5.23×             | 2.03       | 22.4              | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×            | 10.21      | 4.5               | 41.4      |
| Palette    | Fast      | 44.6      | 2.98×             | 1.02       | **44.6**          | ∞         |
| Palette    | Balanced  | 44.4      | 3.00×             | 1.14       | 40.0              | ∞         |
| Palette    | Extreme   | 44.1      | 3.02×             | 1.85       | 24.5              | ∞         |
| Raw        | Any       | 133.2     | 1.00×             | ~1.78      | ~25.5             | ∞         |

**Observations**:
- **Wavelet Balanced** is the best balance of size, speed, and quality: 13.7 MB, 3.05 s, 41.4 dB.
- **Palette Fast** is the fastest configuration: 44.6 MP/s, 44.6 MB — suitable for flat graphics.
- Predictive and Raw modes produce lossless output (∞ PSNR) but with larger files.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31× ratio  |
| **Fastest encode**    | Palette Fast                | 44.6 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 14.9 MP/s    |
| **Best quality**      | Q9 Balanced                 | 76.4 dB PSNR          |
| **Lossless smallest** | Predictive Fast             | 24.6 MB, 5.41× ratio  |

---

## Known constraints

- All tests were run with **scalar** code paths. The test CPU supports AVX2, but the current wheel does not enable it. Preliminary estimates suggest 2.5–3× throughput gains once AVX2 and NEON optimizations land.
- File sizes are still being tuned. The encoder produces correct output, but the compression search logic is not yet fully optimized for all images.
- These numbers represent one 45 MP photograph. Real-world performance varies with image content, resolution, and available threads.
