# WIMF Benchmark Report

**Date**: 2026-08-04  
**Test System**: Intel i5-4460 (Haswell, 4 cores, 2014)  
**RAM**: 32 GB  
**Python**: 3.14.6  
**WIMF Version**: 2.2  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 4  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  
**Measurement methodology**: Each configuration was encoded and decoded five times; the reported values are the median of the three middle runs.

---

## Overview

These benchmarks measure the current state of the WIMF encoder on a representative consumer CPU from 2014. All numbers were collected with the published PyPI wheel (no local compiler involved). The SIMD path was reported as `scalar`; no platform-specific vector extensions were used. RAM was not a limiting factor in any test; peak memory usage remained well below available system memory.

---

## Fast preset – speed-first encoding

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 41.4      | 3.22×             | 2.13       | 0.60       | 21.4              | 67.6      |
| Q9      | 40.7      | 3.27×             | 2.56       | 0.76       | 17.7              | 62.8      |
| Q8      | 40.3      | 3.30×             | 3.11       | 0.72       | 14.6              | 59.8      |
| Q7      | 40.0      | 3.33×             | 2.01       | 0.56       | 22.6              | 57.6      |
| Q6      | 39.8      | 3.34×             | 1.92       | 0.53       | 23.6              | 55.9      |
| Q5      | 39.6      | 3.36×             | 1.82       | 0.51       | 25.0              | 54.5      |
| Q4      | 39.5      | 3.37×             | 1.71       | 0.44       | 26.5              | 53.4      |
| Q3      | 39.4      | 3.38×             | 1.82       | 0.49       | 25.0              | 52.5      |
| Q2      | 39.3      | 3.39×             | 1.70       | 0.45       | 26.7              | 51.7      |
| Q1      | 39.2      | 3.40×             | 1.78       | 0.44       | 25.5              | 51.1      |

**Observations**:
- Peak encode throughput: **26.7 MP/s** (Q2 Fast).
- All Fast runs complete in under 3.2 seconds.
- PSNR ranges from 51.1 dB (Q1) to 67.6 dB (Q10), with diminishing returns beyond Q7.

---

## Balanced preset – default quality/speed trade-off

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 26.1      | 5.11×             | 3.82       | 0.85       | 11.9              | ∞         |
| Q9      | 26.1      | 5.11×             | 3.77       | 0.85       | 12.0              | **76.4**  |
| Q8      | 26.0      | 5.12×             | 3.73       | 0.88       | 12.2              | 63.2      |
| Q7      | 25.8      | 5.16×             | 3.69       | 0.90       | 12.3              | 57.9      |
| Q6      | 25.6      | 5.20×             | 3.68       | 0.93       | 12.3              | 55.9      |
| Q5      | 25.5      | 5.23×             | 3.67       | 0.90       | 12.4              | 54.5      |
| Q4      | 25.4      | 5.25×             | 3.68       | 0.90       | 12.4              | 53.4      |
| Q3      | 25.3      | 5.27×             | 3.66       | 0.90       | 12.4              | 52.5      |
| Q2      | 25.2      | 5.29×             | 3.65       | 0.89       | 12.4              | 51.7      |
| Q1      | 25.6      | 5.20×             | 3.67       | 0.86       | 12.4              | 56.0      |

**Observations**:
- Throughput is stable at **~12.4 MP/s** for Q1–Q8.
- Q9 Balanced delivers **76.4 dB PSNR** with a 5.11× compression ratio — visually lossless for most content.
- This preset is the recommended default for daily use.

---

## Extreme preset – maximum compression

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 24.2      | 5.50×             | 22.66      | 0.85       | 2.0               | ∞         |
| Q9      | 23.0      | 5.79×             | 20.97      | 1.92       | 2.2               | 51.0      |
| Q8      | 18.4      | 7.23×             | 18.59      | 2.27       | 2.4               | 46.5      |
| Q7      | 15.3      | 8.72×             | 17.41      | 2.24       | 2.6               | 44.4      |
| Q6      | 13.0      | 10.22×            | 16.02      | 2.20       | 2.8               | 42.7      |
| Q5      | 11.3      | 11.80×            | 15.05      | 2.18       | 3.0               | 41.4      |
| Q4      | 9.8       | 13.52×            | 14.82      | 2.18       | 3.1               | 40.3      |
| Q3      | 8.7       | 15.36×            | 13.75      | 2.15       | 3.3               | 39.4      |
| Q2      | **7.7**   | **17.31×**        | 13.30      | 2.14       | 3.4               | 38.7      |
| Q1      | 19.3      | 6.89×             | 13.07      | 1.28       | 3.5               | 45.8      |

**Observations**:
- Best compression: **17.31×** at Q2 (7.7 MB).
- Encode times range from 13.1 to 22.7 seconds.
- PSNR drops below 40 dB only at Q2; Q3 and above remain above 39 dB.

---

## Codec‑specific comparison (Q5, all presets)

| Codec      | Preset    | Size (MB) | Compression ratio | Encode (s) | Throughput (MP/s) | PSNR (dB) |
|------------|-----------|----------:|------------------:|-----------:|------------------:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72×             | 4.98       | 9.1               | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31×             | 4.66       | 9.7               | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×            | 8.60       | 5.3               | 41.4      |
| Predictive | Fast      | 24.6      | 5.41×             | 2.29       | 19.9              | ∞         |
| Predictive | Balanced  | 26.1      | 5.09×             | 2.63       | 17.3              | ∞         |
| Predictive | Extreme   | 24.2      | 5.50×             | 5.60       | 8.1               | ∞         |
| Auto       | Fast      | 39.6      | 3.36×             | 1.69       | 26.9              | 54.5      |
| Auto       | Balanced  | 25.5      | 5.23×             | 3.67       | 12.4              | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×            | 15.05      | 3.0               | 41.4      |
| Palette    | Fast      | 44.6      | 2.98×             | 1.21       | **37.7**          | ∞         |
| Palette    | Balanced  | 44.4      | 3.00×             | 1.39       | 32.7              | ∞         |
| Palette    | Extreme   | 44.1      | 3.02×             | 2.01       | 22.6              | ∞         |
| Raw        | Any       | 133.2     | 1.00×             | ~2.07      | ~22               | ∞         |

**Observations**:
- **Wavelet Balanced** is the best balance of size, speed, and quality: 13.7 MB, 4.98 s, 41.4 dB.
- **Palette Fast** is the fastest configuration: 37.7 MP/s, 44.6 MB — suitable for flat graphics.
- Predictive and Raw modes produce lossless output (∞ PSNR) but with larger files.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31× ratio  |
| **Fastest encode**    | Palette Fast                | 37.7 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 9.1 MP/s     |
| **Best quality**      | Q9 Balanced                 | 76.4 dB PSNR          |
| **Lossless smallest** | Predictive Fast             | 24.6 MB, 5.41× ratio  |

---

## Known constraints

- All tests were run with **scalar** code paths. The test CPU supports AVX2, but the current wheel does not enable it. Preliminary estimates suggest 2.5–3× throughput gains once AVX2 and NEON optimizations land.
- File sizes are still being tuned. The encoder produces correct output, but the compression search logic is not yet fully optimized for all images.
- These numbers represent one 45 MP photograph. Real-world performance varies with image content, resolution, and available threads.
