// WIMF v2 NEON kernels. NEON is part of the AArch64 baseline, so this
// translation unit needs no special compiler flags.

#include "v2_simd.hpp"

#if defined(WIMF_NEON)

#include <arm_neon.h>

namespace wimf::v2::simd::neon {

uint64_t left_filter_cost(const uint8_t* row, size_t width) noexcept {
    if (width == 0) return 0;
    uint64_t cost = row[0] <= 128 ? row[0] : 256u - row[0];
    uint32x4_t acc = vdupq_n_u32(0);
    const uint8x16_t zero = vdupq_n_u8(0);
    size_t x = 1;
    for (; x + 15 < width; x += 16) {
        const uint8x16_t cur = vld1q_u8(row + x);
        const uint8x16_t left = vld1q_u8(row + x - 1);
        const uint8x16_t diff = vsubq_u8(cur, left);
        const uint8x16_t negated = vsubq_u8(zero, diff);
        // Pairwise-widen the wrapped absolute values into u16, then fold into
        // u32 lanes (each lane grows by at most 1020 per iteration).
        acc = vpadalq_u16(acc, vpaddlq_u8(vminq_u8(diff, negated)));
    }
    const uint64x2_t total = vpaddlq_u32(acc);
    cost += vgetq_lane_u64(total, 0);
    cost += vgetq_lane_u64(total, 1);
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
    for (; x + 15 < width; x += 16) {
        const uint8x16_t cur = vld1q_u8(row + x);
        const uint8x16_t left = vld1q_u8(row + x - 1);
        vst1q_u8(out + x, vsubq_u8(cur, left));
    }
    for (; x < width; ++x) out[x] = static_cast<uint8_t>(row[x] - row[x - 1]);
}

}  // namespace wimf::v2::simd::neon

#endif  // WIMF_NEON
