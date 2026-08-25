// WIMF v2 AVX2 kernels.
//
// GCC, Clang, and AppleClang enable AVX2 per function via
// '__attribute__((target("avx2")))' so no global compiler flag is needed and
// other translation units stay baseline-portable. AppleClang rejects the
// GCC-style '#pragma GCC target' form, which is why the attribute is applied
// to each kernel directly. MSVC has no per-function ISA selection, so the
// build system must compile this file with '/arch:AVX2' (CMake scopes that
// flag to this file only). The whole unit is skipped unless
// WIMF_SIMD_ENABLE_AVX2 is defined.

#include "v2_simd.hpp"

#if defined(WIMF_AVX2_KERNELS)

#if defined(_MSC_VER) && !defined(__AVX2__)
#error "WIMF_SIMD_ENABLE_AVX2 requires /arch:AVX2 when compiling with MSVC"
#endif

#if defined(_MSC_VER)
#define WIMF_AVX2_TARGET
#define WIMF_AVX2_PCLMUL_TARGET
#else
#define WIMF_AVX2_TARGET __attribute__((target("avx2")))
#define WIMF_AVX2_PCLMUL_TARGET __attribute__((target("avx2,pclmul")))
#endif

#include <immintrin.h>

namespace wimf::v2::simd::avx2 {

WIMF_AVX2_TARGET uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept {
    if (width == 0) return 0;
    uint64_t cost = row[0] <= 128 ? row[0] : 256u - row[0];
    const __m256i zero = _mm256_setzero_si256();
    __m256i acc = zero;
    size_t x = 1;
    for (; x + 31 < width; x += 32) {
        const __m256i cur = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(row + x));
        const __m256i left = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(row + x - 1));
        const __m256i diff = _mm256_sub_epi8(cur, left);
        const __m256i negated = _mm256_sub_epi8(zero, diff);
        // min_u8(diff, -diff) is the wrapped absolute value; SAD against zero
        // then widens each byte magnitude into 64-bit lanes without overflow.
        acc = _mm256_add_epi64(acc, _mm256_sad_epu8(_mm256_min_epu8(diff, negated), zero));
    }
    const __m128i lo = _mm256_castsi256_si128(acc);
    const __m128i hi = _mm256_extracti128_si256(acc, 1);
    const __m128i sum = _mm_add_epi64(lo, hi);
    cost += static_cast<uint64_t>(_mm_extract_epi64(sum, 0));
    cost += static_cast<uint64_t>(_mm_extract_epi64(sum, 1));
    for (; x < width; ++x) {
        const uint8_t residual = static_cast<uint8_t>(row[x] - row[x - 1]);
        cost += residual <= 128 ? residual : 256u - residual;
    }
    return cost;
}

WIMF_AVX2_TARGET void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept {
    if (width == 0) return;
    out[0] = row[0];
    size_t x = 1;
    for (; x + 31 < width; x += 32) {
        const __m256i cur = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(row + x));
        const __m256i left = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(row + x - 1));
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(out + x), _mm256_sub_epi8(cur, left));
    }
    for (; x < width; ++x) out[x] = static_cast<uint8_t>(row[x] - row[x - 1]);
}

// PCLMULQDQ folded CRC-32 (IEEE 802.3, reflected). Structure adapted from
// PHP's crc32_x86.c (BSD-3-Clause, (c) The PHP Group, author Frank Du),
// which follows "Fast CRC Computation for Generic Polynomials Using
// PCLMULQDQ", V. Gopal et al., 2009. Processes floor(size/16)*16 bytes and
// returns the consumed count; callers chain any remainder through the
// scalar table. Verified locally against the slice-by-8 table on 170 size
// cases plus the 0xCBF43926 check vector.
WIMF_AVX2_PCLMUL_TARGET size_t crc32_pclmul(uint32_t* crc, const uint8_t* p, size_t nr) noexcept {
    const uint64_t k1k2[2] = {0x0154442bd4ull, 0x01c6e41596ull};
    const uint64_t k3k4[2] = {0x01751997d0ull, 0x00ccaa009eull};
    const uint64_t k5k6[2] = {0x0163cd6124ull, 0x01db710640ull};
    const uint64_t uPx[2]  = {0x01f7011641ull, 0x01db710641ull};
    const size_t nr_in = nr;
    if (nr < 16) return 0;
    __m128i x0 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p));
    x0 = _mm_xor_si128(x0, _mm_cvtsi32_si128(static_cast<int>(*crc)));
    p += 16; nr -= 16;
    if (nr >= 48) {
        __m128i x1 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p));
        __m128i x2 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p + 16));
        __m128i x3 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p + 32));
        p += 48; nr -= 48;
        const __m128i k = _mm_loadu_si128(reinterpret_cast<const __m128i*>(k1k2));
        while (nr >= 64) {
            __m128i x4 = _mm_clmulepi64_si128(x0, k, 0x00);
            __m128i x5 = _mm_clmulepi64_si128(x1, k, 0x00);
            __m128i x6 = _mm_clmulepi64_si128(x2, k, 0x00);
            __m128i x7 = _mm_clmulepi64_si128(x3, k, 0x00);
            x0 = _mm_clmulepi64_si128(x0, k, 0x11);
            x1 = _mm_clmulepi64_si128(x1, k, 0x11);
            x2 = _mm_clmulepi64_si128(x2, k, 0x11);
            x3 = _mm_clmulepi64_si128(x3, k, 0x11);
            const __m128i x8 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p));
            const __m128i x9 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p + 16));
            const __m128i x10 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p + 32));
            const __m128i x11 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p + 48));
            x0 = _mm_xor_si128(x0, x4); x1 = _mm_xor_si128(x1, x5);
            x2 = _mm_xor_si128(x2, x6); x3 = _mm_xor_si128(x3, x7);
            x0 = _mm_xor_si128(x0, x8); x1 = _mm_xor_si128(x1, x9);
            x2 = _mm_xor_si128(x2, x10); x3 = _mm_xor_si128(x3, x11);
            p += 64; nr -= 64;
        }
        const __m128i kf = _mm_loadu_si128(reinterpret_cast<const __m128i*>(k3k4));
        __m128i x4 = _mm_clmulepi64_si128(x0, kf, 0x00);
        x0 = _mm_clmulepi64_si128(x0, kf, 0x11);
        x0 = _mm_xor_si128(x0, x1); x0 = _mm_xor_si128(x0, x4);
        x4 = _mm_clmulepi64_si128(x0, kf, 0x00);
        x0 = _mm_clmulepi64_si128(x0, kf, 0x11);
        x0 = _mm_xor_si128(x0, x2); x0 = _mm_xor_si128(x0, x4);
        x4 = _mm_clmulepi64_si128(x0, kf, 0x00);
        x0 = _mm_clmulepi64_si128(x0, kf, 0x11);
        x0 = _mm_xor_si128(x0, x3); x0 = _mm_xor_si128(x0, x4);
    }
    const __m128i kf = _mm_loadu_si128(reinterpret_cast<const __m128i*>(k3k4));
    while (nr >= 16) {
        const __m128i x2 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(p));
        const __m128i x1 = _mm_clmulepi64_si128(x0, kf, 0x00);
        x0 = _mm_clmulepi64_si128(x0, kf, 0x11);
        x0 = _mm_xor_si128(x0, x2); x0 = _mm_xor_si128(x0, x1);
        p += 16; nr -= 16;
    }
    __m128i x1 = _mm_clmulepi64_si128(x0, kf, 0x10);
    x0 = _mm_srli_si128(x0, 8);
    x0 = _mm_xor_si128(x0, x1);
    const __m128i kr = _mm_loadu_si128(reinterpret_cast<const __m128i*>(k5k6));
    x1 = _mm_shuffle_epi32(x0, 0xfc);
    x0 = _mm_shuffle_epi32(x0, 0xf9);
    x1 = _mm_clmulepi64_si128(x1, kr, 0x00);
    x0 = _mm_xor_si128(x0, x1);
    x1 = _mm_shuffle_epi32(x0, 0xf3);
    x0 = _mm_slli_si128(x0, 4);
    const __m128i ku = _mm_loadu_si128(reinterpret_cast<const __m128i*>(uPx));
    x1 = _mm_clmulepi64_si128(x1, ku, 0x00);
    x1 = _mm_clmulepi64_si128(x1, ku, 0x10);
    x0 = _mm_xor_si128(x1, x0);
    *crc = static_cast<uint32_t>(_mm_extract_epi32(x0, 2));
    return nr_in - nr;
}

}  // namespace wimf::v2::simd::avx2

#endif  // WIMF_AVX2_KERNELS
