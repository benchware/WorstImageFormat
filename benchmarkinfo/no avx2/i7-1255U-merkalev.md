# WIMF Benchmark Report — Fujitsu LIFEBOOK E5412 (Core i7-1255U)

**Date**: 2026-08-05  
**Test System**: Fujitsu LIFEBOOK E5412  
**CPU**: Intel Core i7-1255U @ 1.70 GHz (10 cores, 12 threads, Alder Lake, 2022)  
**RAM**: 32 GB DDR4 (31.6 GB usable)  
**Storage**: NVMe SSD  
**GPU**: Intel Iris Xe (not used by WIMF)  
**OS**: Microsoft Windows 11 Pro (Build 22631)  
**Python**: 3.14.6  
**WIMF Version**: 2.2  
**Native Backend**: C++17, scalar (no AVX2, NEON, or AVX-512)  
**Threads**: 8  
**Power Source**: AC adapter (plugged in)  
**Image**: 8256 × 5504 (45.4 MP), RGB, source: NASA ART002-E-15971.JPG  

**Note**: Stock power limits. No ThrottleStop, no undervolt, no external cooling. Ambient ~16°C with AC.

---

## Fast preset

| Quality | Size (MB) | Ratio | Encode (s) | Decode (s) | MP/s | PSNR (dB) |
|--------:|----------:|------:|-----------:|-----------:|-----:|----------:|
| Q10     | 41.4      | 3.22× | 1.11       | 0.33       | 40.9 | 67.6      |
| Q9      | 40.7      | 3.27× | 1.20       | 0.37       | 37.9 | 62.8      |
| Q8      | 40.3      | 3.30× | 1.18       | 0.34       | 38.4 | 59.8      |
| Q7      | 40.0      | 3.33× | 1.16       | 0.34       | 39.3 | 57.6      |
| Q6      | 39.8      | 3.34× | 1.18       | 0.34       | 38.4 | 55.9      |
| Q5      | 39.6      | 3.36× | 1.17       | 0.33       | 39.0 | 54.5      |
| Q4      | 39.5      | 3.37× | 1.12       | 0.32       | 40.6 | 53.4      |
| Q3      | 39.4      | 3.38× | 1.11       | 0.34       | 41.0 | 52.5      |
| Q2      | 39.3      | 3.39× | 1.13       | 0.33       | 40.1 | 51.7      |
| Q1      | 39.2      | 3.40× | **1.10**   | 0.34       | **41.3** | 51.1 |

**Observations**: Peak encode 41.3 MP/s. All runs under 1.2s.

---

## Balanced preset

| Quality | Size (MB) | Ratio | Encode (s) | Decode (s) | MP/s | PSNR (dB) |
|--------:|----------:|------:|-----------:|-----------:|-----:|----------:|
| Q10     | 26.1      | 5.11× | 2.34       | 0.57       | 19.4 | ∞         |
| Q9      | 26.1      | 5.11× | 2.32       | 0.57       | 19.6 | **76.4**  |
| Q8      | 26.0      | 5.12× | 2.38       | 0.63       | 19.1 | 63.2      |
| Q7      | 25.8      | 5.16× | 2.40       | 0.64       | 18.9 | 57.9      |
| Q6      | 25.6      | 5.20× | 2.38       | 0.62       | 19.1 | 55.9      |
| Q5      | 25.5      | 5.23× | 2.29       | 0.62       | 19.8 | 54.5      |
| Q4      | 25.4      | 5.25× | 2.35       | 0.65       | 19.3 | 53.4      |
| Q3      | 25.3      | 5.27× | 2.31       | 0.63       | 19.7 | 52.5      |
| Q2      | 25.2      | 5.29× | 2.29       | 0.61       | 19.8 | 51.7      |
| Q1      | 25.6      | 5.20× | 2.25       | 0.59       | **20.2** | 56.0 |

**Observations**: Stable ~19–20 MP/s. Q9 delivers 76.4 dB.

---

## Extreme preset

| Quality | Size (MB) | Ratio | Encode (s) | Decode (s) | MP/s | PSNR (dB) |
|--------:|----------:|------:|-----------:|-----------:|-----:|----------:|
| Q10     | 24.2      | 5.50× | 16.87      | 0.57       | 2.7  | ∞         |
| Q9      | 23.0      | 5.79× | 14.90      | 1.49       | 3.0  | 51.0      |
| Q8      | 18.4      | 7.23× | 14.15      | 2.01       | 3.2  | 46.5      |
| Q7      | 15.3      | 8.72× | 13.55      | 1.96       | 3.4  | 44.4      |
| Q6      | 13.0      | 10.22×| 12.73      | 1.94       | 3.6  | 42.7      |
| Q5      | 11.3      | 11.80×| 11.62      | 1.86       | 3.9  | 41.4      |
| Q4      | 9.8       | 13.52×| 10.91      | 1.82       | 4.2  | 40.3      |
| Q3      | 8.7       | 15.36×| 10.37      | 1.78       | 4.4  | 39.4      |
| Q2      | **7.7**   | **17.31×**| **9.67** | 1.76 | **4.7** | 38.7 |
| Q1      | 19.3      | 6.89× | 9.87       | 1.01       | 4.6  | 45.8      |

**Observations**: Best compression 17.31× at Q2 (7.7 MB) in 9.67s. Peak throughput 4.7 MP/s.

---

## Codec comparison (Q5)

| Codec      | Preset    | Size (MB) | Ratio | Encode (s) | MP/s | PSNR (dB) |
|------------|-----------|----------:|------:|-----------:|-----:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72× | 3.71       | 12.3 | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31× | 3.70       | 12.3 | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×| 6.63       | 6.9  | 41.4      |
| Predictive | Fast      | 24.6      | 5.41× | 1.42       | 32.0 | ∞         |
| Predictive | Balanced  | 26.1      | 5.09× | 1.68       | 27.1 | ∞         |
| Predictive | Extreme   | 24.2      | 5.50× | 3.96       | 11.5 | ∞         |
| Auto       | Fast      | 39.6      | 3.36× | 1.17       | 38.7 | 54.5      |
| Auto       | Balanced  | 25.5      | 5.23× | 2.34       | 19.4 | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×| 11.28      | 4.0  | 41.4      |
| Palette    | Fast      | 44.6      | 2.98× | **0.92**   | **49.6** | ∞ |
| Palette    | Balanced  | 44.4      | 3.00× | 1.04       | 43.6 | ∞         |
| Palette    | Extreme   | 44.1      | 3.02× | 1.55       | 29.4 | ∞         |
| Raw        | Any       | 133.2     | 1.00× | ~1.5       | ~29  | ∞         |

**Observations**: Palette Fast fastest at 49.6 MP/s. Wavelet Balanced best balance at 13.7 MB, 12.3 MP/s.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31×        |
| **Fastest encode**    | Palette Fast                | **49.6 MP/s**         |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 12.3 MP/s    |
| **Best quality**      | Q9 Balanced                 | 76.4 dB               |
| **Lossless smallest** | Auto Extreme                | 24.2 MB, 5.50×        |

---

## Hardware context

| **Component** | **Details** |
|---------------|-------------|
| **CPU** | Intel Core i7-1255U @ 1.70 GHz (Alder Lake, 2022) |
| **Cores/Threads** | 10 cores, 12 threads (2 P-cores + 8 E-cores) |
| **TDP** | 15W base, 55W max turbo (stock) |
| **RAM** | 32 GB DDR4 |
| **Storage** | NVMe SSD |
| **OS** | Windows 11 Pro (Build 22631) |
| **BIOS** | FUJITSU Version 2.35 (01/07/2025) |
| **Power Source** | AC adapter (plugged in) |

---

## Known constraints

- All tests run with **scalar** code paths.
- **No ThrottleStop** — stock Fujitsu power management.
- Ambient ~16°C with AC.
- Hybrid architecture may not be fully utilized.
- Results represent one 45 MP image.

---

## Reproducibility

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
```
