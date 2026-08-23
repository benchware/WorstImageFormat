#include "v2_simd.hpp"

#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>

namespace simd = wimf::v2::simd;

namespace {

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void test_crc32_vectors() {
    struct Vector {
        const char* data;
        uint32_t expected;
    };
    // IEEE 802.3 reflected CRC-32 reference vectors.
    const Vector vectors[] = {
        {"", 0x00000000u},
        {"123456789", 0xCBF43926u},
        {"The quick brown fox jumps over the lazy dog", 0x414FA339u},
    };
    for (const Vector& vector : vectors) {
        const auto* bytes = reinterpret_cast<const uint8_t*>(vector.data);
        const size_t size = std::strlen(vector.data);
        require(simd::crc32(bytes, size) == vector.expected, "dispatched CRC-32 vector failed");
        require(simd::crc32_table(bytes, size) == vector.expected, "table CRC-32 vector failed");
#if defined(WIMF_NEON)
        if (simd::has_hardware_crc32())
            require(simd::crc32_hw::compute(bytes, size) == vector.expected,
                    "hardware CRC-32 vector failed");
#endif
    }
}

void test_crc32_bulk_consistency() {
    std::mt19937 rng(20260823);
    std::vector<uint8_t> blob(1024 * 1024 + 3);
    for (uint8_t& byte : blob) byte = static_cast<uint8_t>(rng());
    const uint32_t table = simd::crc32_table(blob.data(), blob.size());
    require(simd::crc32(blob.data(), blob.size()) == table,
            "dispatched CRC-32 diverged from the table implementation");
#if defined(WIMF_NEON)
    if (simd::has_hardware_crc32())
        require(simd::crc32_hw::compute(blob.data(), blob.size()) == table,
                "hardware CRC-32 diverged from the table implementation");
#endif
}

void test_left_filter_kernels_match_scalar() {
    std::mt19937 rng(987654321);
    // Sweep every width across the 16/32-byte kernel boundaries plus tails.
    for (size_t width = 0; width <= 300; ++width) {
        std::vector<uint8_t> row(width), reference(width), accelerated(width);
        for (uint8_t& byte : row) byte = static_cast<uint8_t>(rng());

        const uint64_t reference_cost =
            simd::scalar::left_filter_cost(row.data(), row.size());
        const uint64_t dispatched_cost = simd::left_filter_cost(row.data(), row.size());
        require(reference_cost == dispatched_cost, "dispatched filter cost diverged");

        simd::scalar::left_filter_emit(row.data(), reference.data(), row.size());
        simd::left_filter_emit(row.data(), accelerated.data(), row.size());
        require(reference == accelerated, "dispatched filter emit diverged");

        if (!row.empty()) {
            std::vector<uint8_t> reconstructed(row.size());
            reconstructed[0] = reference[0];
            for (size_t x = 1; x < row.size(); ++x)
                reconstructed[x] = static_cast<uint8_t>(reconstructed[x - 1] + reference[x]);
            require(reconstructed == row, "filter emit did not invert");
        }
    }
}

void test_runtime_probes_report_compiled_backends() {
#if !defined(WIMF_AVX2_KERNELS)
    require(!simd::has_avx2(), "AVX2 reported without compiled kernels");
#endif
#if !defined(WIMF_NEON)
    require(!simd::has_hardware_crc32(), "hardware CRC reported outside an ARM build");
#endif
}

}  // namespace

int main() {
    try {
        test_crc32_vectors();
        test_crc32_bulk_consistency();
        test_left_filter_kernels_match_scalar();
        test_runtime_probes_report_compiled_backends();
        std::cout << "All native WIMF v2 SIMD tests passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Native SIMD test failure: " << error.what() << '\n';
        return 1;
    }
}
