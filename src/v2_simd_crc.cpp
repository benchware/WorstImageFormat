// WIMF v2 ARMv8 CRC-32 extension kernels.
//
// The hardware path is only compiled when the toolchain guarantees the CRC
// instruction set (__ARM_FEATURE_CRC32). Availability is probed at runtime on
// Linux so a '+crc' build still runs safely on CPUs without the extension;
// everywhere else the compile-time contract of the macro applies. When the
// extension was not compiled in, supported() reports false and callers use
// the scalar table.

#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE 1
#endif

#include "v2_simd.hpp"

#if defined(WIMF_NEON)

#include <cstring>

#if defined(__linux__)
#include <sys/auxv.h>
#ifndef HWCAP_CRC32
#define HWCAP_CRC32 (1u << 7)
#endif
#endif

#if defined(__ARM_FEATURE_CRC32)
#include <arm_acle.h>
#endif

namespace wimf::v2::simd::crc32_hw {

#if defined(__ARM_FEATURE_CRC32)

uint32_t compute(const uint8_t* data, size_t size) noexcept {
    uint32_t crc = 0xFFFFFFFFu;
    while (size >= 8) {
        uint64_t value;
        std::memcpy(&value, data, sizeof(value));
        crc = __crc32d(crc, value);
        data += sizeof(value);
        size -= sizeof(value);
    }
    if (size >= 4) {
        uint32_t value;
        std::memcpy(&value, data, sizeof(value));
        crc = __crc32w(crc, value);
        data += sizeof(value);
        size -= sizeof(value);
    }
    while (size--) crc = __crc32b(crc, *data++);
    return ~crc;
}

bool supported() noexcept {
#if defined(__linux__)
    // HWCAP_CRC32 (AT_HWCAP bit 7) reports kernel + CPU support.
    return (getauxval(AT_HWCAP) & HWCAP_CRC32) != 0;
#else
    // Apple silicon and every other toolchain that predefines the macro
    // guarantee it as part of the target baseline.
    return true;
#endif
}

#else  // __ARM_FEATURE_CRC32

uint32_t compute(const uint8_t*, size_t) noexcept { return 0; }
bool supported() noexcept { return false; }

#endif

}  // namespace wimf::v2::simd::crc32_hw

#endif  // WIMF_NEON
