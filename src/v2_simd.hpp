#pragma once
// WIMF v2 SIMD acceleration â€” internal header.
//
// Instruction-set-specific kernels are isolated in dedicated translation
// units so vector code can never leak into baseline compilation:
//
//   v2_simd_avx2.cpp  x86-64 AVX2 kernels (in-source '#pragma GCC target',
//                     or MSVC '/arch:AVX2' scoped to that file)
//   v2_simd_neon.cpp  AArch64 NEON kernels (baseline ISA, no flags needed)
//   v2_simd_crc.cpp   AArch64 CRC-32 extension (optional, runtime-probed)
//   v2_simd.cpp       scalar reference kernels, CPU feature probing, dispatch
//
// Every public entry point is safe to call on any host: dispatch falls back
// to scalar whenever a kernel was compiled out or the CPU lacks the feature.

#include <cstddef>
#include <cstdint>

#if defined(__aarch64__) || defined(_M_ARM64)
#define WIMF_NEON 1
#endif

#if defined(WIMF_SIMD_ENABLE_AVX2) && (defined(__x86_64__) || defined(_M_X64))
#define WIMF_AVX2_KERNELS 1
#endif

namespace wimf::v2::simd {

// Runtime feature probes. They reflect what this binary actually executes:
// has_avx2() is false when the AVX2 kernels were compiled out, even if the
// CPU supports the instruction set.
bool has_avx2() noexcept;
bool has_hardware_crc32() noexcept;

// Scalar reference kernels; also the universal fallback.
namespace scalar {
uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept;
void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept;
}  // namespace scalar

// Lookup-table CRC-32 (IEEE 802.3, reflected, init/final XOR 0xFFFFFFFF).
uint32_t crc32_table(const uint8_t* data, size_t size) noexcept;

#if defined(WIMF_AVX2_KERNELS)
// Requires has_avx2() to be true before use.
namespace avx2 {
uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept;
void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept;
}  // namespace avx2
#endif

#if defined(WIMF_NEON)
// NEON is part of the AArch64 baseline; always callable there.
namespace neon {
uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept;
void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept;
}  // namespace neon
// ARMv8 CRC-32 crypto-extension kernels. compute() is only valid while
// has_hardware_crc32() is true.
namespace crc32_hw {
uint32_t compute(const uint8_t* data, size_t size) noexcept;
bool supported() noexcept;
}  // namespace crc32_hw
#endif

// Dispatched entry points used by the codec core.
uint32_t crc32(const uint8_t* data, size_t size) noexcept;
uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept;
void left_filter_emit(const uint8_t* row, uint8_t* out, size_t width) noexcept;

}  // namespace wimf::v2::simd
