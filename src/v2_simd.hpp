#pragma once
// WIMF v2 SIMD acceleration â€” internal header.
// Provides optimised CRC-32 and predictive-filter helpers for NEON and AVX2.

#include <cstddef>
#include <cstdint>
#include <cstring>

// â”€â”€ Platform detection â”€â”€

#if defined(__aarch64__) || defined(_M_ARM64)
#define WIMF_NEON 1
#include <arm_neon.h>
#if defined(__ARM_FEATURE_CRC32)
#include <arm_acle.h>
#define WIMF_ARM_CRC 1
#endif

#elif defined(__AVX2__)
#define WIMF_AVX2 1
#ifdef _MSC_VER
#include <intrin.h>
#else
#include <immintrin.h>
#endif
#endif

namespace wimf::v2::simd {

// â”€â”€ CRC-32 (lookup-table, ~8Ã— faster than bit-at-a-time) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

namespace detail {
constexpr uint32_t crc_entry(uint32_t i) {
    for (int k = 0; k < 8; ++k) i = (i >> 1) ^ (0xEDB88320u & -(i & 1u));
    return i;
}
struct CrcTable {
    uint32_t t[256];
    constexpr CrcTable() : t{} { for (uint32_t i = 0; i < 256; ++i) t[i] = crc_entry(i); }
};
constexpr CrcTable kCrc{};
}  // namespace detail

inline uint32_t crc32_table(const uint8_t* data, size_t size) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < size; ++i)
        crc = (crc >> 8) ^ detail::kCrc.t[static_cast<uint8_t>(crc ^ data[i])];
    return ~crc;
}

#if defined(WIMF_ARM_CRC)
inline uint32_t crc32_hw(const uint8_t* data, size_t size) {
    uint32_t crc = 0xFFFFFFFFu;
    while (size >= 8) { uint64_t v; std::memcpy(&v, data, 8); crc = __crc32d(crc, v); data += 8; size -= 8; }
    while (size >= 4) { uint32_t v; std::memcpy(&v, data, 4); crc = __crc32w(crc, v); data += 4; size -= 4; }
    while (size--) crc = __crc32b(crc, *data++);
    return ~crc;
}
#endif

inline uint32_t crc32_fast(const uint8_t* data, size_t size) {
#if defined(WIMF_ARM_CRC)
    return crc32_hw(data, size);
#else
    return crc32_table(data, size);
#endif
}

// â”€â”€ Predictive filter: left-predictor cost & residual emit (8-bit) â”€â”€â”€â”€

#if defined(WIMF_AVX2)

inline uint64_t left_filter_cost_avx2(const uint8_t* row, size_t width) {
    if (width == 0) return 0;
    uint64_t cost = row[0] <= 128 ? row[0] : 256u - row[0];
    const __m256i zero = _mm256_setzero_si256();
    __m256i acc = zero;
    size_t x = 1;
    for (; x + 31 < width; x += 32) {
        __m256i cur  = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(row + x));
        __m256i left = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(row + x - 1));
        __m256i r    = _mm256_sub_epi8(cur, left);
        __m256i neg  = _mm256_sub_epi8(zero, r);
        acc = _mm256_add_epi64(acc, _mm256_sad_epu8(_mm256_min_epu8(r, neg), zero));
    }
    __m128i lo = _mm256_castsi256_si128(acc), hi = _mm256_extracti128_si256(acc, 1);
    __m128i s  = _mm_add_epi64(lo, hi);
    cost += static_cast<uint64_t>(_mm_extract_epi64(s, 0)) + static_cast<uint64_t>(_mm_extract_epi64(s, 1));
    for (; x < width; ++x) { uint8_t r = static_cast<uint8_t>(row[x] - row[x - 1]); cost += r <= 128 ? r : 256u - r; }
    return cost;
}

inline void left_filter_emit_avx2(const uint8_t* row, uint8_t* out, size_t width) {
    if (width == 0) return;
    out[0] = row[0];
    size_t x = 1;
    for (; x + 31 < width; x += 32) {
        __m256i cur  = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(row + x));
        __m256i left = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(row + x - 1));
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(out + x), _mm256_sub_epi8(cur, left));
    }
    for (; x < width; ++x) out[x] = static_cast<uint8_t>(row[x] - row[x - 1]);
}

#endif  // WIMF_AVX2

#if defined(WIMF_NEON)

inline uint64_t left_filter_cost_neon(const uint8_t* row, size_t width) {
    if (width == 0) return 0;
    uint64_t cost = row[0] <= 128 ? row[0] : 256u - row[0];
    uint32x4_t acc = vdupq_n_u32(0);
    const uint8x16_t vzero = vdupq_n_u8(0);
    size_t x = 1;
    for (; x + 15 < width; x += 16) {
        uint8x16_t cur  = vld1q_u8(row + x);
        uint8x16_t left = vld1q_u8(row + x - 1);
        uint8x16_t r    = vsubq_u8(cur, left);
        uint8x16_t neg  = vsubq_u8(vzero, r);
        acc = vpadalq_u16(acc, vpaddlq_u8(vminq_u8(r, neg)));
    }
    uint64x2_t s64 = vpaddlq_u32(acc);
    cost += vgetq_lane_u64(s64, 0) + vgetq_lane_u64(s64, 1);
    for (; x < width; ++x) { uint8_t r = static_cast<uint8_t>(row[x] - row[x - 1]); cost += r <= 128 ? r : 256u - r; }
    return cost;
}

inline void left_filter_emit_neon(const uint8_t* row, uint8_t* out, size_t width) {
    if (width == 0) return;
    out[0] = row[0];
    size_t x = 1;
    for (; x + 15 < width; x += 16) {
        uint8x16_t cur  = vld1q_u8(row + x);
        uint8x16_t left = vld1q_u8(row + x - 1);
        vst1q_u8(out + x, vsubq_u8(cur, left));
    }
    for (; x < width; ++x) out[x] = static_cast<uint8_t>(row[x] - row[x - 1]);
}

#endif  // WIMF_NEON

// â”€â”€ Dispatch to best available â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

inline uint64_t left_filter_cost(const uint8_t* row, size_t width) {
#if defined(WIMF_AVX2)
    return left_filter_cost_avx2(row, width);
#elif defined(WIMF_NEON)
    return left_filter_cost_neon(row, width);
#else
    if (width == 0) return 0;
    uint64_t cost = row[0] <= 128 ? row[0] : 256u - row[0];
    for (size_t x = 1; x < width; ++x) { uint8_t r = static_cast<uint8_t>(row[x] - row[x - 1]); cost += r <= 128 ? r : 256u - r; }
    return cost;
#endif
}

inline void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) {
#if defined(WIMF_AVX2)
    left_filter_emit_avx2(row, out, width);
#elif defined(WIMF_NEON)
    left_filter_emit_neon(row, out, width);
#else
    if (width == 0) return;
    out[0] = row[0];
    for (size_t x = 1; x < width; ++x) out[x] = static_cast<uint8_t>(row[x] - row[x - 1]);
#endif
}

}  // namespace wimf::v2::simd

