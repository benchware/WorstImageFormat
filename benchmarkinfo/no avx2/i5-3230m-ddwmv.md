# WIMF Benchmark Report — Intel Core i5-3230M (2012 Laptop)

**Date**: 2026-08-04  
**Test System**: Dell Latitude E6530 (2012 business laptop)  
**CPU**: Intel Core i5-3230M @ 2.60 GHz (2 cores, 4 threads, Ivy Bridge, 2012)  
**RAM**: 8 GB DDR3-1333 (dual-channel, Samsung)  
**Storage**: Samsung SSD 840 (120 GB)  
**GPU**: Intel HD Graphics 4000 (not used by WIMF)  
**OS**: Microsoft Windows 11 Pro 23H2 (Build 22631.6199)  
**Python**: 3.14.6  
**WIMF Version**: 2.2  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 4  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  

**Note**: This system was released in 2012 — 14 years old at the time of testing. It runs Windows 11 through unsupported hardware workarounds. The fact it runs at all is a minor miracle.

---

## Overview

These benchmarks measure the current state of the WIMF encoder on a 14-year-old laptop CPU with slow DDR3-1333 memory. All numbers were collected with the published PyPI wheel (no local compiler involved). The SIMD path was reported as `scalar`; no platform-specific vector extensions were used. RAM was not a limiting factor in any test.

---

## Fast preset – speed-first encoding

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 41.4      | 3.22×             | 3.50       | 1.04       | 13.0              | 67.6      |
| Q9      | 40.7      | 3.27×             | 4.47       | 1.64       | 10.2              | 62.8      |
| Q8      | 40.3      | 3.30×             | 3.31       | 1.01       | 13.7              | 59.8      |
| Q7      | 40.0      | 3.33×             | 3.12       | 0.91       | 14.6              | 57.6      |
| Q6      | 39.8      | 3.34×             | 3.20       | 0.89       | 14.2              | 55.9      |
| Q5      | 39.6      | 3.36×             | 3.14       | 0.91       | 14.5              | 54.5      |
| Q4      | 39.5      | 3.37×             | 3.12       | 0.90       | 14.6              | 53.4      |
| Q3      | 39.4      | 3.38×             | 3.10       | 0.88       | 14.7              | 52.5      |
| Q2      | 39.3      | 3.39×             | 3.09       | 0.88       | 14.7              | 51.7      |
| Q1      | 39.2      | 3.40×             | 3.01       | 0.87       | **15.1**          | 51.1      |

**Observations**:
- Peak encode throughput: **15.1 MP/s** (Q1 Fast).
- All Fast runs complete in under 4.5 seconds.
- This is a 14-year-old laptop with DDR3-1333. **15 MP/s is absurd.**
- PSNR ranges from 51.1 dB (Q1) to 67.6 dB (Q10).

---

## Balanced preset – default quality/speed trade-off

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 26.1      | 5.11×             | 8.46       | 1.79       | 5.4               | ∞         |
| Q9      | 26.1      | 5.11×             | 8.29       | 1.78       | 5.5               | **76.4**  |
| Q8      | 26.0      | 5.12×             | 8.24       | 1.95       | 5.5               | 63.2      |
| Q7      | 25.8      | 5.16×             | 8.24       | 1.91       | 5.5               | 57.9      |
| Q6      | 25.6      | 5.20×             | 8.18       | 1.96       | 5.6               | 55.9      |
| Q5      | 25.5      | 5.23×             | 8.21       | 1.93       | 5.5               | 54.5      |
| Q4      | 25.4      | 5.25×             | 8.10       | 2.03       | 5.6               | 53.4      |
| Q3      | 25.3      | 5.27×             | 8.07       | 2.10       | 5.6               | 52.5      |
| Q2      | 25.2      | 5.29×             | 8.09       | 1.94       | 5.6               | 51.7      |
| Q1      | 25.6      | 5.20×             | 8.07       | 1.83       | 5.6               | 56.0      |

**Observations**:
- Throughput is stable at **~5.5 MP/s** across all qualities.
- Q9 Balanced delivers **76.4 dB PSNR** with a 5.11× compression ratio.
- This preset is the recommended default for daily use — even on a 14-year-old laptop.

---

## Extreme preset – maximum compression

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 24.2      | 5.50×             | 57.12      | 2.19       | 0.8               | ∞         |
| Q9      | 23.0      | 5.79×             | 50.21      | 4.68       | 0.9               | 51.0      |
| Q8      | 18.4      | 7.23×             | 45.13      | 5.59       | 1.0               | 46.5      |
| Q7      | 15.3      | 8.72×             | 41.88      | 5.53       | 1.1               | 44.4      |
| Q6      | 13.0      | 10.22×            | 45.04      | 6.14       | 1.0               | 42.7      |
| Q5      | 11.3      | 11.80×            | 37.51      | 5.68       | 1.2               | 41.4      |
| Q4      | 9.8       | 13.52×            | 35.86      | 5.56       | 1.3               | 40.3      |
| Q3      | 8.7       | 15.36×            | 34.56      | 5.44       | 1.3               | 39.4      |
| Q2      | **7.7**   | **17.31×**        | **33.41**  | 5.46       | **1.4**           | 38.7      |
| Q1      | 19.3      | 6.89×             | 33.02      | 3.03       | 1.4               | 45.8      |

**Observations**:
- Best compression: **17.31×** at Q2 (7.7 MB) in **33.4 seconds**.
- Peak throughput on Extreme: **1.4 MP/s**.
- Encode times range from 33 to 57 seconds — acceptable for archival on old hardware.

---

## Codec‑specific comparison (Q5, all presets)

| Codec      | Preset    | Size (MB) | Compression ratio | Encode (s) | Throughput (MP/s) | PSNR (dB) |
|------------|-----------|----------:|------------------:|-----------:|------------------:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72×             | 12.32      | 3.7               | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31×             | 11.78      | 3.9               | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×            | 21.20      | 2.1               | 41.4      |
| Predictive | Fast      | 24.6      | 5.41×             | 4.94       | 9.2               | ∞         |
| Predictive | Balanced  | 26.1      | 5.09×             | 5.98       | 7.6               | ∞         |
| Predictive | Extreme   | 24.2      | 5.50×             | 14.43      | 3.1               | ∞         |
| Auto       | Fast      | 39.6      | 3.36×             | 3.14       | 14.5              | 54.5      |
| Auto       | Balanced  | 25.5      | 5.23×             | 8.21       | 5.5               | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×            | 37.51      | 1.2               | 41.4      |
| Palette    | Fast      | 44.6      | 2.98×             | 2.20       | **20.6**          | ∞         |
| Palette    | Balanced  | 44.4      | 3.00×             | 2.81       | 16.2              | ∞         |
| Palette    | Extreme   | 44.1      | 3.02×             | 4.54       | 10.0              | ∞         |
| Raw        | Any       | 133.2     | 1.00×             | ~3.85      | ~11.8             | ∞         |

**Observations**:
- **Palette Fast** is the fastest configuration: **20.6 MP/s**, 44.6 MB — suitable for flat graphics.
- **Auto Fast** is the best practical configuration: **14.5 MP/s**, 39.6 MB.
- **Wavelet Balanced** is the best size/speed/quality balance: 13.7 MB, 12.32 s.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31× ratio  |
| **Fastest encode**    | Palette Fast                | 20.6 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 3.7 MP/s     |
| **Best quality**      | Q9 Balanced                 | 76.4 dB PSNR          |
| **Lossless smallest** | Predictive Fast             | 24.6 MB, 5.41× ratio  |

---

## Known constraints

- All tests were run with **scalar** code paths. The test CPU does not support AVX2.
- This is a 14-year-old laptop with DDR3-1333. Performance is **remarkably good** for its age.
- File sizes are still being tuned. The encoder produces correct output, but the compression search logic is not yet fully optimized for all images.
- **Windows 11 23H2** running on unsupported hardware is a testament to the user's persistence.

---

## Hardware context

| **Component** | **Details** |
|---------------|-------------|
| **CPU** | Intel Core i5-3230M @ 2.60 GHz (Ivy Bridge, 2012) |
| **Cores/Threads** | 2 cores, 4 threads |
| **TDP** | 35W |
| **RAM** | 8 GB DDR3-1333 (dual-channel) |
| **OS** | Windows 11 Pro 23H2 (unsupported hardware) |
| **Age at test** | 14 years |
