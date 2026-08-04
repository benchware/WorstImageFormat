# WIMF Benchmark Rankings

**Last Updated**: 2026-08-04

Rankings based on 45.4 MP (8256×5504) NASA test image, using WIMF 2.2 native C++ backend. All systems running scalar code — no AVX2, NEON, or AVX-512 acceleration.

---

## Overall Rankings (Fast Preset — Q1)

| Rank | System | CPU | Year | Cores/Threads | RAM | OS | Throughput (MP/s) | Encode Time (s) |
|------|--------|-----|------|---------------|-----|----|------------------|-----------------|
| 1 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | 2023 | 4C/8T | 8 GB LPDDR5-5500 | CachyOS Linux | **45.2** | 1.01 |
| 2 | Custom Desktop | Intel Core i5-8400 | 2017 | 6C/6T | 16 GB DDR4-3200 | Windows 10 | 44.6 | 1.02 |
| 3 | Custom Desktop | Intel Core i5-4460 | 2014 | 4C/4T | 32 GB DDR3-1600 | Windows 10 | 26.7 | 1.21 |
| 4 | HP ProDesk 600 G3 | Intel Core i3-7100T | 2017 | 2C/4T | 16 GB DDR4-2400 | CachyOS Linux | 22.6 | 1.73 |
| 5 | Dell Latitude E6530 | Intel Core i5-3230M | 2012 | 2C/4T | 8 GB DDR3-1333 | Windows 11 | 15.1 | 2.20 |
| 6 | Intel NUC7i3BNH | Intel Core i3-7100U | 2016 | 2C/4T | 8 GB DDR4-2133 | Proxmox Linux | 13.1 | 2.96 |
| 7 | Custom Desktop | Intel Core i3-3240 | 2012 | 2C/4T | 16 GB DDR3-1600 | Windows 11 | 7.0 | 4.15 |

---

## Balanced Preset Rankings (Q5 — Recommended Default)

| Rank | System | CPU | Throughput (MP/s) | Encode Time (s) | Compression Ratio |
|------|--------|-----|------------------|-----------------|-------------------|
| 1 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | **41.0** | 1.11 | 3.00× |
| 2 | Custom Desktop | Intel Core i5-8400 | 22.5 | 2.03 | 5.23× |
| 3 | Custom Desktop | Intel Core i5-4460 | 12.4 | 3.67 | 5.23× |
| 4 | HP ProDesk 600 G3 | Intel Core i3-7100T | 10.2 | 4.51 | 5.23× |
| 5 | Intel NUC7i3BNH | Intel Core i3-7100U | 6.6 | 6.91 | 5.23× |
| 6 | Dell Latitude E6530 | Intel Core i5-3230M | 5.6 | 8.21 | 5.23× |
| 7 | Custom Desktop | Intel Core i3-3240 | 3.5 | 14.07 | 5.24× |

---

## Extreme Preset Rankings (Q2 — Best Compression)

| Rank | System | CPU | Throughput (MP/s) | Encode Time (s) | Compression Ratio |
|------|--------|-----|------------------|-----------------|-------------------|
| 1 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | **7.3** | 6.22 | 17.31× |
| 2 | Custom Desktop | Intel Core i5-8400 | 5.5 | 8.21 | 17.31× |
| 3 | Custom Desktop | Intel Core i5-4460 | 3.4 | 13.30 | 17.31× |
| 4 | HP ProDesk 600 G3 | Intel Core i3-7100T | 3.1 | 14.81 | 17.31× |
| 5 | Intel NUC7i3BNH | Intel Core i3-7100U | 2.0 | 22.24 | 17.31× |
| 6 | Dell Latitude E6530 | Intel Core i5-3230M | 1.4 | 33.41 | 17.31× |
| 7 | Custom Desktop | Intel Core i3-3240 | 0.5 | 100.94 | 17.31× |

---

## Best Codec-Specific Performance (Q5)

| System | CPU | Codec | Preset | Throughput (MP/s) | Size (MB) |
|--------|-----|-------|--------|-------------------|-----------|
| Vivobook Go | Ryzen 3 7320U | Palette | Fast | **45.2** | 44.6 |
| i5-8400 | i5-8400 | Palette | Fast | 44.6 | 44.6 |
| i5-4460 | i5-4460 | Palette | Fast | 37.7 | 44.6 |
| i3-7100T | i3-7100T | Palette | Fast | 26.3 | 44.6 |
| i5-3230M | i5-3230M | Palette | Fast | 20.6 | 44.6 |
| i3-7100U | i3-7100U | Palette | Fast | 15.3 | 44.6 |
| i3-3240 | i3-3240 | Palette | Fast | 10.9 | 44.6 |

---

## Fastest Decode Speed (Q5)

| Rank | System | CPU | Decode Throughput (MP/s) | Config |
|------|--------|-----|--------------------------|--------|
| 1 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | **231.0** | Palette Balanced |
| 2 | Custom Desktop | Intel Core i5-8400 | 157.3 | Palette Balanced |
| 3 | Custom Desktop | Intel Core i5-4460 | 141.2 | Palette Fast |
| 4 | HP ProDesk 600 G3 | Intel Core i3-7100T | 136.8 | Palette Balanced |
| 5 | Intel NUC7i3BNH | Intel Core i3-7100U | 73.1 | Palette Fast |
| 6 | Custom Desktop | Intel Core i3-3240 | 72.7 | Raw Extreme |
| 7 | Dell Latitude E6530 | Intel Core i5-3230M | 65.2 | Palette Fast |

---

## Key Observations

1. **AMD Ryzen 3 7320U dominates**: Highest throughput across all presets, despite being a budget laptop chip.
2. **Palette codec is fastest**: Consistently achieves the highest throughput on all systems.
3. **Extreme preset is compression-focused**: All systems achieve the same 17.31× compression ratio at Q2.
4. **Windows vs Linux**: Linux systems (CachyOS) tend to perform better than Windows on the same architecture.
5. **Newer architectures win**: Zen 2 and Coffee Lake outperform older Haswell and Ivy Bridge CPUs.
6. **Decode speed scales with CPU**: Newer CPUs decode significantly faster than older ones.

---

## System Efficiency (Performance per Watt)

| Rank | System | CPU | TDP | Fast Throughput (MP/s) | Efficiency (MP/s per W) |
|------|--------|-----|-----|----------------------|------------------------|
| 1 | Vivobook Go | Ryzen 3 7320U | 15W | 45.2 | **3.01** |
| 2 | i5-8400 | i5-8400 | 65W | 44.6 | 0.69 |
| 3 | i3-7100T | i3-7100T | 35W | 22.6 | 0.65 |
| 4 | i3-7100U | i3-7100U | 15W | 13.1 | 0.87 |
| 5 | i5-3230M | i5-3230M | 35W | 15.1 | 0.43 |
| 6 | i5-4460 | i5-4460 | 84W | 26.7 | 0.32 |
| 7 | i3-3240 | i3-3240 | 55W | 7.0 | 0.13 |

---

## Projected Performance with AVX2/NEON

| System | CPU | Current (Scalar) | Projected (AVX2/NEON) | Speedup |
|--------|-----|------------------|-----------------------|---------|
| Vivobook Go | Ryzen 3 7320U | 45.2 MP/s | **~90-135 MP/s** | 2-3× |
| i5-8400 | i5-8400 | 44.6 MP/s | **~90-130 MP/s** | 2-3× |
| i5-4460 | i5-4460 | 26.7 MP/s | **~60-80 MP/s** | 2-3× |
| i3-7100T | i3-7100T | 22.6 MP/s | **~50-70 MP/s** | 2-3× |
| i3-7100U | i3-7100U | 13.1 MP/s | **~30-40 MP/s** | 2-3× |

---

## Notes

- All benchmarks run with **scalar** code paths — AVX2/NEON are not yet enabled.
- Performance numbers are hardware-dependent and may vary.
- Rankings will be updated as new systems are tested.
- Compression ratios are based on Q2 Extreme preset unless otherwise noted.
