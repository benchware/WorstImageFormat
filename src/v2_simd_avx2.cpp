// WIMF v2 AVX2 kernels.
//
// GCC/Clang enable AVX2 in-source via '#pragma GCC target' so no global
// compiler flag is needed and other translation units stay baseline-portable.
// MSVC has no per-function ISA selection, so the build system must compile
// this file with '/arch:AVX2' (CMake scopes that flag to this file only).
// The whole unit is skipped unless WIMF_SIMD_ENABLE_AVX2 is defined.

#include "v2_simd.hpp"

#if defined(WIMF_AVX2_KERNELS)

#if defined(_MSC_VER) && !defined(__AVX2__)
#error "WIMF_SIMD_ENABLE_AVX2 requires /arch:AVX2 when compiling with MSVC"
#endif

#if defined(__GNUC__) || defined(__clang__)
#pragma GCC push_options
#pragma GCC target("avx2")
#endif

#include <immintrin.h>

namespace wimf::v2::simd::avx2 {

uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept {
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

void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept {
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

}  // namespace wimf::v2::simd::avx2

#if defined(__GNUC__) || defined(__clang__)
#pragma GCC pop_options
#endif

#endif  // WIMF_AVX2_KERNELS
