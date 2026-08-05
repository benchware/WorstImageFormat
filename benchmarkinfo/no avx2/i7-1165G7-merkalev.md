# WIMF Benchmark Report — Fujitsu LIFEBOOK E5411 (Core i7-1165G7)

**Date**: 2026-08-05  
**Test System**: Fujitsu LIFEBOOK E5411  
**CPU**: Intel Core i7-1165G7 @ 2.80 GHz (4 cores, 8 threads, Tiger Lake, 2020)  
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
| Q10     | 41.4      | 3.22× | 1.14       | 0.29       | 39.7 | 67.6      |
| Q9      | 40.7      | 3.27× | 1.09       | 0.29       | 41.6 | 62.8      |
| Q8      | 40.3      | 3.30× | 1.11       | 0.30       | 40.8 | 59.8      |
| Q7      | 40.0      | 3.33× | 1.14       | 0.27       | 39.7 | 57.6      |
| Q6      | 39.8      | 3.34× | 1.09       | 0.27       | 41.6 | 55.9      |
| Q5      | 39.6      | 3.36× | 1.10       | 0.29       | 41.2 | 54.5      |
| Q4      | 39.5      | 3.37× | 1.10       | 0.28       | 41.4 | 53.4      |
| Q3      | 39.4      | 3.38× | 1.09       | 0.27       | 41.7 | 52.5      |
| Q2      | 39.3      | 3.39× | **1.08**   | 0.29       | **42.0** | 51.7 |
| Q1      | 39.2      | 3.40× | 1.09       | 0.28       | 41.8 | 51.1      |

**Observations**: Peak encode 42.0 MP/s. All runs under 1.15s.

---

## Balanced preset

| Quality | Size (MB) | Ratio | Encode (s) | Decode (s) | MP/s | PSNR (dB) |
|--------:|----------:|------:|-----------:|-----------:|-----:|----------:|
| Q10     | 26.1      | 5.11× | 2.21       | 0.46       | 20.6 | ∞         |
| Q9      | 26.1      | 5.11× | 2.15       | 0.47       | **21.1** | **76.4** |
| Q8      | 26.0      | 5.12× | 2.35       | 0.58       | 19.4 | 63.2      |
| Q7      | 25.8      | 5.16× | 2.67       | 0.60       | 17.0 | 57.9      |
| Q6      | 25.6      | 5.20× | 2.70       | 0.60       | 16.8 | 55.9      |
| Q5      | 25.5      | 5.23× | 2.74       | 0.62       | 16.6 | 54.5      |
| Q4      | 25.4      | 5.25× | 2.71       | 0.71       | 16.8 | 53.4      |
| Q3      | 25.3      | 5.27× | 2.54       | 0.58       | 17.9 | 52.5      |
| Q2      | 25.2      | 5.29× | 2.53       | 0.59       | 18.0 | 51.7      |
| Q1      | 25.6      | 5.20× | 2.57       | 0.56       | 17.7 | 56.0      |

**Observations**: Stable ~17–21 MP/s. Q9 delivers 76.4 dB.

---

## Extreme preset

| Quality | Size (MB) | Ratio | Encode (s) | Decode (s) | MP/s | PSNR (dB) |
|--------:|----------:|------:|-----------:|-----------:|-----:|----------:|
| Q10     | 24.2      | 5.50× | 17.40      | 0.62       | 2.6  | ∞         |
| Q9      | 23.0      | 5.79× | 15.51      | 1.53       | 2.9  | 51.0      |
| Q8      | 18.4      | 7.23× | 15.35      | 1.87       | 3.0  | 46.5      |
| Q7      | 15.3      | 8.72× | 13.32      | 1.78       | 3.4  | 44.4      |
| Q6      | 13.0      | 10.22×| 16.18      | 3.31       | 2.8  | 42.7      |
| Q5      | 11.3      | 11.80×| 15.63      | 2.31       | 2.9  | 41.4      |
| Q4      | 9.8       | 13.52×| 11.62      | 1.77       | 3.9  | 40.3      |
| Q3      | 8.7       | 15.36×| 10.43      | 1.74       | 4.4  | 39.4      |
| Q2      | **7.7**   | **17.31×**| **10.04** | 1.74 | **4.5** | 38.7 |
| Q1      | 19.3      | 6.89× | 10.02      | 1.02       | 4.5  | 45.8      |

**Observations**: Best compression 17.31× at Q2 (7.7 MB) in 10.04s. Peak throughput 4.5 MP/s.

---

## Codec comparison (Q5)

| Codec      | Preset    | Size (MB) | Ratio | Encode (s) | MP/s | PSNR (dB) |
|------------|-----------|----------:|------:|-----------:|-----:|----------:|
| Wavelet    | Balanced  | 13.7      | 9.72× | 3.75       | 12.1 | 41.4      |
| Wavelet    | Fast      | 16.0      | 8.31× | 3.63       | 12.5 | 41.4      |
| Wavelet    | Extreme   | 11.3      | 11.80×| 6.62       | 6.9  | 41.4      |
| Predictive | Fast      | 24.6      | 5.41× | 1.48       | 30.6 | ∞         |
| Predictive | Balanced  | 26.1      | 5.09× | 1.81       | 25.2 | ∞         |
| Predictive | Extreme   | 24.2      | 5.50× | 4.50       | 10.1 | ∞         |
| Auto       | Fast      | 39.6      | 3.36× | 1.10       | **41.2** | 54.5 |
| Auto       | Balanced  | 25.5      | 5.23× | 2.74       | 16.6 | 54.5      |
| Auto       | Extreme   | 11.3      | 11.80×| 15.63      | 2.9  | 41.4      |
| Palette    | Fast      | 44.6      | 2.98× | 0.95       | 48.0 | ∞         |
| Palette    | Balanced  | 44.4      | 3.00× | 1.09       | 41.7 | ∞         |
| Palette    | Extreme   | 44.1      | 3.02× | 1.67       | 27.2 | ∞         |
| Raw        | Any       | 133.2     | 1.00× | ~1.6       | ~28  | ∞         |

**Observations**: Auto Fast fastest at 41.2 MP/s. Palette Fast 48.0 MP/s. Wavelet Balanced best balance at 13.7 MB, 12.1 MP/s.

---

## Summary of best results

| Category              | Configuration               | Value                 |
|-----------------------|-----------------------------|-----------------------|
| **Smallest file**     | Q2 Extreme                  | 7.7 MB, 17.31×        |
| **Fastest encode**    | Auto Fast                   | 42.0 MP/s             |
| **Best balance**      | Q5 Wavelet Balanced         | 13.7 MB, 12.1 MP/s    |
| **Best quality**      | Q9 Balanced                 | 76.4 dB               |
| **Lossless smallest** | Auto Extreme                | 24.2 MB, 5.50×        |

---

## Hardware context

| **Component** | **Details** |
|---------------|-------------|
| **CPU** | Intel Core i7-1165G7 @ 2.80 GHz (Tiger Lake, 2020) |
| **Cores/Threads** | 4 cores, 8 threads |
| **TDP** | 15W base, 28W max turbo (stock) |
| **RAM** | 32 GB DDR4 |
| **Storage** | NVMe SSD |
| **OS** | Windows 11 Pro (Build 22631) |
| **BIOS** | FUJITSU Version 2.40 (03/09/2024) |
| **Power Source** | AC adapter (plugged in) |

---

## Known constraints

- All tests run with **scalar** code paths.
- **No ThrottleStop** — stock Fujitsu power management.
- Ambient ~16°C with AC.
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
