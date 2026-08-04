# WIMF Benchmark Report — Intel NUC7i3BNH (Core i3-7100U)

**Date**: 2026-08-04  
**Test System**: Intel NUC7i3BNH (Mini PC, 2016)  
**CPU**: Intel Core i3-7100U @ 2.40 GHz (2 cores, 4 threads, Kaby Lake, 2016)  
**RAM**: 8 GB DDR4-2133 (dual-channel, SK Hynix + Samsung)  
**Storage**: 225 GB SSD (ext4)  
**GPU**: Intel HD Graphics 620 (not used by WIMF)  
**OS**: Proxmox VE 9.2.3 (Linux 7.0.12-1-pve)  
**Python**: 3.13.5  
**WIMF Version**: 2.2  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 4  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  
**Measurement methodology**: Each configuration was encoded and decoded five times; the reported values are the median of the three middle runs.

---

## Overview

These benchmarks measure the current state of the WIMF encoder on a low-power 15W Intel NUC from 2016. The system runs Proxmox VE (virtualized environment) and was tested with the published PyPI wheel. The SIMD path was reported as `scalar`; no platform-specific vector extensions were used.

Despite being the lowest-power system in the benchmark suite, the NUC achieved respectable performance with excellent power efficiency.

---

## Fast preset – speed-first encoding

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 41.4      | 3.22×             | 3.73       | 0.92       | 12.2              | 67.6      |
| Q9      | 40.7      | 3.27×             | 3.58       | 0.77       | 12.7              | 62.8      |
| Q8      | 40.3      | 3.30×             | 3.50       | 0.70       | 13.0              | 59.8      |
| Q7      | 40.0      | 3.33×             | 3.53       | 0.71       | 12.9              | 57.6      |
| Q6      | 39.8      | 3.34×             | 3.48       | 0.71       | 13.1              | 55.9      |
| Q5      | 39.6      | 3.36×             | 3.63       | 0.70       | 12.5              | 54.5      |
| Q4      | 39.5      | 3.37×             | 3.48       | 0.69       | 13.0              | 53.4      |
| Q3      | 39.4      | 3.38×             | 3.49       | 0.70       | 13.0              | 52.5      |
| Q2      | 39.3      | 3.39×             | 3.59       | 0.69       | 12.6              | 51.7      |
| Q1      | 39.2      | 3.40×             | **3.47**   | 0.69       | **13.1**          | 51.1      |

**Observations**:
- Peak encode throughput: **13.1 MP/s** (Q1 Fast).
- All Fast runs complete in under 3.8 seconds.
- PSNR ranges from 51.1 dB (Q1) to 67.6 dB (Q10), with diminishing returns beyond Q7.

---

## Balanced preset – default quality/speed trade-off

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 26.1      | 5.11×             | 6.86       | 1.30       | 6.6               | ∞         |
| Q9      | 26.1      | 5.11×             | 7.00       | 1.27       | 6.5               | **76.4**  |
| Q8      | 26.0      | 5.12×             | 6.90       | 1.30       | 6.6               | 63.2      |
| Q7      | 25.8      | 5.16×             | 6.93       | 1.31       | 6.6               | 57.9      |
| Q6      | 25.6      | 5.20×             | 6.83       | 1.34       | 6.6               | 55.9      |
| Q5      | 25.5      | 5.23×             | 6.91       | 1.31       | 6.6               | 54.5      |
| Q4      | 25.4      | 5.25×             | 6.82       | 1.32       | 6.7               | 53.4      |
| Q3      | 25.3      | 5.27×             | 6.77       | 1.31       | 6.7               | 52.5      |
| Q2      | 25.2      | 5.29×             | 6.68       | 1.31       | 6.8               | 51.7      |
| Q1      | 25.6      | 5.20×             | 6.75       | 1.40       | 6.7               | 56.0      |

**Observations**:
- Throughput is stable at **~6.6 MP/s** across all qualities.
- Q9 Balanced delivers **76.4 dB PSNR** with a 5.11× compression ratio — visually lossless for most content.
- This preset is the recommended default for daily use on low-power systems.

---

## Extreme preset – maximum compression

| Quality | Size (MB) | Compression ratio | Encode (s) | Decode (s) | Throughput (MP/s) | PSNR (dB) |
|--------:|----------:|------------------:|-----------:|-----------:|------------------:|----------:|
| Q10     | 24.2      | 5.50×             | 39.94      | 1.27       | 1.1               | ∞         |
| Q9      | 23.0      | 5.79×             | 35.76      | 2.36       | 1.3               | 51.0      |
| Q8      | 18.4      | 7.23×             | 33.33      | 2.86       | 1.4               | 46.5      |
| Q7      | 15.3      | 8.72×             | 32.24      | 2.79       | 1.4               | 44.4      |
| Q6      | 13.0      | 10.22×            | 30.03      | 2.43       | 1.5               | 42.7      |
| Q5      | 11.3      | 11.80×            | 26.49      | 2.36       | 1.7               | 41.4      |
| Q4      | 9.8       | 13.52×            | 24.40      | 2.31       | 1.9               | 40.3      |
| Q3      | 8.7       | 15.36×            | 22.90      | 2.31       | 2.0               | 39.4      |
| Q2      | **7.7**   | **17.31×**        | **22.24**  | 2.27       | **2.0**           | 38.7      |
| Q1      | 19.3      | 6.89×             | 21.74      | 1.70       | 2.1               | 45.8      |

**Observations**:
- Best compression: **17.31×** at Q2 (7.7 MB) in **22.24 seconds**.
- Peak throughput on Extreme: **2.1 MP/s** at Q1.
- Encode times range from 21.7 to 39.9 seconds — acceptable for archival on low-power hardware.

---

## Codec‑specific comparison (Q5, all presets)

| Codec      | Preset    | Size (MB) | Compression ratio | Encode (s) | Throughput (MP/s) | PSNR (dB) |
|------------|-----------|----------:|------------------:|-----------:|------------------:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72×             | 5.23       | **8.7**           | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31×             | 4.66       | 9.8               | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×            | 12.64      | 3.6               | 41.4      |
| Predictive | Fast      | 24.6      | 5.41×             | 3.32       | 13.7              | ∞         |
| Predictive | Balanced  | 26.1      | 5.09×             | 4.06       | 11.2              | ∞         |
| Predictive | Extreme   | 24.2      | 5.50×             | 9.97       | 4.6               | ∞         |
| Auto       | Fast      | 39.6      | 3.36×             | 3.63       | 12.5              | 54.5      |
| Auto       | Balanced  | 25.5      | 5.23×             | 6.91       | 6.6               | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×            | 26.49      | 1.7               | 41.4      |
| Palette    | Fast      | 44.6      | 2.98×             | 2.96       | **15.3**          | ∞         |
| Palette    | Balanced  | 44.4      | 3.00×             | 3.29       | 13.8              | ∞         |
| Palette    | Extreme   | 44.1      | 3.02×             | 4.52       | 10.0              | ∞         |
| Raw        | Any       | 133.2     | 1.00×             | ~2.79      | ~16.3             | ∞         |

**Observations**:
- **Palette Fast** is the fastest configuration: **15.3 MP/s**, 44.6 MB — suitable for flat graphics.
- **Wavelet Balanced** is the best balance of size, speed, and quality: 13.7 MB, 5.23 s, 41.4 dB.
- **Auto Fast** delivers 12.5 MP/s with 54.5 dB PSNR — excellent for general use.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31× ratio  |
| **Fastest encode**    | Palette Fast                | 15.3 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 8.7 MP/s     |
| **Best quality**      | Q9 Balanced                 | 76.4 dB PSNR          |
| **Lossless smallest** | Predictive Fast             | 24.6 MB, 5.41× ratio  |

---

## Hardware context

| **Component** | **Details** |
|---------------|-------------|
| **CPU** | Intel Core i3-7100U @ 2.40 GHz (Kaby Lake, 2016) |
| **Cores/Threads** | 2 cores, 4 threads |
| **TDP** | 15W |
| **RAM** | 8 GB DDR4-2133 (dual-channel) |
| **RAM Modules** | SK Hynix + Samsung |
| **Storage** | 225 GB SSD |
| **OS** | Proxmox VE 9.2.3 (virtualized) |
| **Kernel** | Linux 7.0.12-1-pve |

---

## Known constraints

- All tests were run with **scalar** code paths. The test CPU does not support AVX2.
- The system runs Proxmox VE, a virtualized environment, which may add some overhead.
- RAM is capped at 2133 MHz (the maximum supported by the CPU/motherboard).
- File sizes are still being tuned. The encoder produces correct output, but the compression search logic is not yet fully optimized for all images.
- These numbers represent one 45 MP photograph. Real-world performance varies with image content, resolution, and available threads.
