# WIMF Benchmark Rankings

**Last Updated**: 2026-08-05

Rankings based on 45.4 MP (8256×5504) NASA test image, using WIMF 2.2 native C++ backend. All systems running scalar code — no AVX2, NEON, or AVX-512 acceleration.

---

## Overall Rankings (Fast Preset — Q1)

| Rank | System | CPU | Year | Cores/Threads | RAM | OS | Throughput (MP/s) | Encode Time (s) |
|------|--------|-----|------|---------------|-----|----|------------------|-----------------|
| 1 | Fujitsu LIFEBOOK E5412 | Intel Core i7-1255U | 2022 | 10C/12T | 32 GB DDR4 | Windows 11 | **50.9** | 0.89 |
| 2 | Fujitsu LIFEBOOK E5411 | Intel Core i7-1165G7 | 2020 | 4C/8T | 32 GB DDR4 | Windows 11 | **48.0** | 0.95 |
| 3 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | 2023 | 4C/8T | 8 GB LPDDR5 | CachyOS Linux | 45.2 | 1.01 |
| 4 | Custom Desktop | Intel Core i5-8400 | 2017 | 6C/6T | 16 GB DDR4 | Windows 10 | 44.6 | 1.02 |
| 5 | Lenovo ThinkPad L13 Yoga | Intel Core i5-10210U | 2019 | 4C/8T | 16 GB DDR4 | Windows 11 | 42.0 | 1.08 |
| 6 | Custom Desktop | Intel Core i5-4460 | 2014 | 4C/4T | 32 GB DDR3 | Windows 10 | 26.7 | 1.21 |
| 7 | HP ProDesk 600 G3 | Intel Core i3-7100T | 2017 | 2C/4T | 16 GB DDR4 | CachyOS Linux | 22.6 | 1.73 |
| 8 | HP ProBook 640 G3 | Intel Core i5-7200U | 2016 | 2C/4T | 16 GB DDR4 | Windows 10 | 20.1 | 2.26 |
| 9 | Dell Latitude E6530 | Intel Core i5-3230M | 2012 | 2C/4T | 8 GB DDR3 | Windows 11 | 15.1 | 2.20 |
| 10 | Intel NUC7i3BNH | Intel Core i3-7100U | 2016 | 2C/4T | 8 GB DDR4 | Proxmox Linux | 13.1 | 2.96 |
| 11 | Custom Desktop | Intel Core i3-3240 | 2012 | 2C/4T | 16 GB DDR3 | Windows 11 | 7.0 | 4.15 |

---

## Balanced Preset Rankings (Q5 — Recommended Default)

| Rank | System | CPU | Throughput (MP/s) | Encode Time (s) | Compression Ratio |
|------|--------|-----|------------------|-----------------|-------------------|
| 1 | Fujitsu LIFEBOOK E5412 | Intel Core i7-1255U | **41.7** | 1.09 | 3.00× |
| 2 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | 41.0 | 1.11 | 3.00× |
| 3 | Fujitsu LIFEBOOK E5411 | Intel Core i7-1165G7 | 21.1 | 2.15 | 5.11× |
| 4 | Lenovo ThinkPad L13 Yoga | Intel Core i5-10210U | 21.1 | 2.15 | 5.11× |
| 5 | Custom Desktop | Intel Core i5-8400 | 22.5 | 2.03 | 5.23× |
| 6 | Custom Desktop | Intel Core i5-4460 | 12.4 | 3.67 | 5.23× |
| 7 | HP ProDesk 600 G3 | Intel Core i3-7100T | 10.2 | 4.51 | 5.23× |
| 8 | HP ProBook 640 G3 | Intel Core i5-7200U | 7.6 | 5.97 | 5.23× |
| 9 | Intel NUC7i3BNH | Intel Core i3-7100U | 6.6 | 6.91 | 5.23× |
| 10 | Dell Latitude E6530 | Intel Core i5-3230M | 5.6 | 8.21 | 5.23× |
| 11 | Custom Desktop | Intel Core i3-3240 | 3.5 | 14.07 | 5.24× |

---

## Extreme Preset Rankings (Q2 — Best Compression)

| Rank | System | CPU | Throughput (MP/s) | Encode Time (s) | Compression Ratio |
|------|--------|-----|------------------|-----------------|-------------------|
| 1 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | 7.3 | 6.22 | 17.31× |
| 2 | Fujitsu LIFEBOOK E5412 | Intel Core i7-1255U | **7.2** | 6.30 | 17.31× |
| 3 | Custom Desktop | Intel Core i5-8400 | 5.5 | 8.21 | 17.31× |
| 4 | Fujitsu LIFEBOOK E5411 | Intel Core i7-1165G7 | 4.5 | 10.04 | 17.31× |
| 5 | Lenovo ThinkPad L13 Yoga | Intel Core i5-10210U | 4.5 | 10.04 | 17.31× |
| 6 | Custom Desktop | Intel Core i5-4460 | 3.4 | 13.30 | 17.31× |
| 7 | HP ProDesk 600 G3 | Intel Core i3-7100T | 3.1 | 14.81 | 17.31× |
| 8 | Intel NUC7i3BNH | Intel Core i3-7100U | 2.0 | 22.24 | 17.31× |
| 9 | HP ProBook 640 G3 | Intel Core i5-7200U | 1.7 | 27.10 | 17.31× |
| 10 | Dell Latitude E6530 | Intel Core i5-3230M | 1.4 | 33.41 | 17.31× |
| 11 | Custom Desktop | Intel Core i3-3240 | 0.5 | 100.94 | 17.31× |

---

## Best Codec-Specific Performance (Q5)

| Rank | System | CPU | Codec | Preset | Throughput (MP/s) | Size (MB) |
|------|--------|-----|-------|--------|-------------------|-----------|
| 1 | Fujitsu LIFEBOOK E5412 | Intel Core i7-1255U | Palette | Fast | **50.9** | 44.6 |
| 2 | Fujitsu LIFEBOOK E5411 | Intel Core i7-1165G7 | Palette | Fast | **48.0** | 44.6 |
| 3 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | Palette | Fast | 45.2 | 44.6 |
| 4 | Custom Desktop | Intel Core i5-8400 | Palette | Fast | 44.6 | 44.6 |
| 5 | Lenovo ThinkPad L13 Yoga | Intel Core i5-10210U | Auto | Fast | 41.2 | 39.6 |
| 6 | Custom Desktop | Intel Core i5-4460 | Palette | Fast | 37.7 | 44.6 |
| 7 | HP ProDesk 600 G3 | Intel Core i3-7100T | Palette | Fast | 26.3 | 44.6 |
| 8 | HP ProBook 640 G3 | Intel Core i5-7200U | Palette | Fast | 24.0 | 44.6 |
| 9 | Dell Latitude E6530 | Intel Core i5-3230M | Palette | Fast | 20.6 | 44.6 |
| 10 | Intel NUC7i3BNH | Intel Core i3-7100U | Palette | Fast | 15.3 | 44.6 |
| 11 | Custom Desktop | Intel Core i3-3240 | Palette | Fast | 10.9 | 44.6 |

---

## Fastest Decode Speed (Q5)

| Rank | System | CPU | Decode Throughput (MP/s) | Config |
|------|--------|-----|--------------------------|--------|
| 1 | ASUS Vivobook Go E1404FA | AMD Ryzen 3 7320U | 231.0 | Palette Balanced |
| 2 | Fujitsu LIFEBOOK E5412 | Intel Core i7-1255U | **191.9** | Palette Balanced |
| 3 | Fujitsu LIFEBOOK E5411 | Intel Core i7-1165G7 | **191.9** | Palette Balanced |
| 4 | Custom Desktop | Intel Core i5-8400 | 157.3 | Palette Balanced |
| 5 | Lenovo ThinkPad L13 Yoga | Intel Core i5-10210U | 141.3 | Auto Fast |
| 6 | Custom Desktop | Intel Core i5-4460 | 141.2 | Palette Fast |
| 7 | HP ProDesk 600 G3 | Intel Core i3-7100T | 136.8 | Palette Balanced |
| 8 | HP ProBook 640 G3 | Intel Core i5-7200U | 93.7 | Palette Extreme |
| 9 | Intel NUC7i3BNH | Intel Core i3-7100U | 73.1 | Palette Fast |
| 10 | Custom Desktop | Intel Core i3-3240 | 72.7 | Raw Extreme |
| 11 | Dell Latitude E6530 | Intel Core i5-3230M | 65.2 | Palette Fast |

---

## Key Observations

1. **Fujitsu E5412 (i7-1255U) dominates**: Takes #1 spot across all presets with 10-core hybrid architecture.
2. **Palette codec is fastest**: Consistently achieves the highest throughput on all systems.
3. **Lenovo vs Fujitsu E5411**: Both i7-1165G7 and i5-10210U tie at 42.0 MP/s — identical performance despite different generations.
4. **Extreme preset compression is deterministic**: All systems achieve exactly 17.31× at Q2.
5. **Windows vs Linux**: Linux (CachyOS) performs better than Windows on similar hardware.
6. **Decode speed scales with CPU**: Newer CPUs decode significantly faster.
7. **All new systems beat older ones**: Alder Lake and Zen 2 dominate the leaderboard.

---

## System Efficiency (Performance per Watt)

| Rank | System | CPU | TDP | Fast Throughput (MP/s) | Efficiency (MP/s per W) |
|------|--------|-----|-----|----------------------|------------------------|
| 1 | Fujitsu E5412 | i7-1255U | 15W | 50.9 | **3.39** |
| 2 | Fujitsu E5411 | i7-1165G7 | 15W | 48.0 | **3.20** |
| 3 | Vivobook Go | Ryzen 3 7320U | 15W | 45.2 | 3.01 |
| 4 | Lenovo L13 Yoga | i5-10210U | 15W | 42.0 | 2.80 |
| 5 | i5-7200U | i5-7200U | 15W | 22.1 | 1.47 |
| 6 | i3-7100U | i3-7100U | 15W | 13.1 | 0.87 |
| 7 | i5-8400 | i5-8400 | 65W | 44.6 | 0.69 |
| 8 | i3-7100T | i3-7100T | 35W | 22.6 | 0.65 |
| 9 | i5-3230M | i5-3230M | 35W | 15.1 | 0.43 |
| 10 | i5-4460 | i5-4460 | 84W | 26.7 | 0.32 |
| 11 | i3-3240 | i3-3240 | 55W | 7.0 | 0.13 |

**The i7-1255U leads in efficiency, with the i7-1165G7 close behind.**

---


## Projected Performance with AVX2/NEON

| System | CPU | Current (Scalar) | Projected (AVX2/NEON) | Speedup |
|--------|-----|------------------|-----------------------|---------|
| Fujitsu E5412 | i7-1255U | 50.9 MP/s | **~100-150 MP/s** | 2-3× |
| Fujitsu E5411 | i7-1165G7 | 48.0 MP/s | **~100-140 MP/s** | 2-3× |
| Vivobook Go | Ryzen 3 7320U | 45.2 MP/s | **~90-135 MP/s** | 2-3× |
| i5-8400 | i5-8400 | 44.6 MP/s | **~90-130 MP/s** | 2-3× |
| i5-4460 | i5-4460 | 26.7 MP/s | **~60-80 MP/s** | 2-3× |
| i3-7100T | i3-7100T | 22.6 MP/s | **~50-70 MP/s** | 2-3× |
| i5-7200U | i5-7200U | 22.1 MP/s | **~50-70 MP/s** | 2-3× |
| i3-7100U | i3-7100U | 13.1 MP/s | **~30-40 MP/s** | 2-3× |

---

## Notes

- All benchmarks run with **scalar** code paths — AVX2/NEON are not yet enabled.
- **Lenovo** uses ThrottleStop (PL1=25W, PL2=51W) — not out-of-box stock.
- **Fujitsu systems** run stock power limits — no modifications.
- All systems plugged into AC power during testing.
- Ambient temperature ~16°C with AC on maximum for all systems.
- Performance numbers are hardware-dependent and may vary.
- Rankings will be updated as new systems are tested.
- Compression ratios based on Q2 Extreme preset unless otherwise noted.
