// WIMF v2 SIMD dispatch â€” scalar reference kernels, CPU feature probing,
// and the runtime-selected entry points used by the codec core.
//
// This translation unit is compiled for the baseline instruction set only;
// it must never emit vector instructions.

#include "v2_simd.hpp"

#if defined(WIMF_AVX2_KERNELS) && defined(_MSC_VER) && !defined(__clang__)
#include <immintrin.h>
#include <intrin.h>
#ifndef _XCR_XFEATURE_ENABLED_MASK
#define _XCR_XFEATURE_ENABLED_MASK 0
#endif
#endif

namespace wimf::v2::simd {
namespace {

constexpr uint32_t crc_entry(uint32_t index) {
    for (int bit = 0; bit < 8; ++bit) index = (index >> 1) ^ (0xEDB88320u & -(index & 1u));
    return index;
}

struct CrcTable {
    uint32_t entries[256];
    constexpr CrcTable() : entries{} {
        for (uint32_t i = 0; i < 256; ++i) entries[i] = crc_entry(i);
    }
};
constexpr CrcTable kCrcTable{};

struct Features {
    bool avx2 = false;
    bool hardware_crc32 = false;
};

#if defined(WIMF_AVX2_KERNELS)

// Full AVX2 availability check: CPU support, OSXSAVE enabled, and an OS that
// saves YMM register state (XCR0 bits 1 and 2).
bool detect_avx2() noexcept {
#if defined(__GNUC__) || defined(__clang__)
    __builtin_cpu_init();
    return __builtin_cpu_supports("avx2") != 0;
#elif defined(_MSC_VER)
    int registers[4] = {0, 0, 0, 0};
    __cpuid(registers, 1);
    constexpr int kOsxsave = 1 << 27, kAvx = 1 << 28;  // ECX bits of leaf 1.
    if ((registers[2] & (kOsxsave | kAvx)) != (kOsxsave | kAvx)) return false;
    const unsigned long long xcr0 = _xgetbv(_XCR_XFEATURE_ENABLED_MASK);
    if ((xcr0 & 0x6ull) != 0x6ull) return false;
    __cpuidex(registers, 7, 0);
    return (registers[1] & (1 << 5)) != 0;  // EBX bit 5: AVX2.
#else
    return false;
#endif
}

#endif  // WIMF_AVX2_KERNELS

Features detect_features() noexcept {
    Features features;
#if defined(WIMF_AVX2_KERNELS)
    features.avx2 = detect_avx2();
#endif
#if defined(WIMF_NEON)
    features.hardware_crc32 = crc32_hw::supported();
#endif
    return features;
}

const Features& features() noexcept {
    static const Features cached = detect_features();  // Thread-safe in C++11+.
    return cached;
}

}  // namespace

bool has_avx2() noexcept { return features().avx2; }
bool has_hardware_crc32() noexcept { return features().hardware_crc32; }

uint32_t crc32_table(const uint8_t* data, size_t size) noexcept {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < size; ++i)
        crc = (crc >> 8) ^ kCrcTable.entries[(crc ^ data[i]) & 0xFFu];
    return ~crc;
}

namespace scalar {

uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept {
    if (width == 0) return 0;
    uint64_t cost = row[0] <= 128 ? row[0] : 256u - row[0];
    for (size_t x = 1; x < width; ++x) {
        const uint8_t residual = static_cast<uint8_t>(row[x] - row[x - 1]);
        cost += residual <= 128 ? residual : 256u - residual;
    }
    return cost;
}

void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept {
    if (width == 0) return;
    out[0] = row[0];
    for (size_t x = 1; x < width; ++x) out[x] = static_cast<uint8_t>(row[x] - row[x - 1]);
}

}  // namespace scalar

#if defined(WIMF_NEON)

uint32_t crc32(const uint8_t* data, size_t size) noexcept {
    if (features().hardware_crc32) return crc32_hw::compute(data, size);
    return crc32_table(data, size);
}

uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept {
    return neon::left_filter_cost(row, width);
}

void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept {
    neon::left_filter_emit(row, out, width);
}

#elif defined(WIMF_AVX2_KERNELS)

uint32_t crc32(const uint8_t* data, size_t size) noexcept { return crc32_table(data, size); }

uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept {
    return features().avx2 ? avx2::left_filter_cost(row, width)
                           : scalar::left_filter_cost(row, width);
}

void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept {
    if (features().avx2)
        avx2::left_filter_emit(row, out, width);
    else
        scalar::left_filter_emit(row, out, width);
}

#else

uint32_t crc32(const uint8_t* data, size_t size) noexcept { return crc32_table(data, size); }

uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept {
    return scalar::left_filter_cost(row, width);
}

void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept {
    scalar::left_filter_emit(row, out, width);
}

#endif

}  // namespace wimf::v2::simd
