#include "v2_simd.hpp"

#include <algorithm>
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

void test_scalar_reference_known_answers() {
    // Hand-computed vectors covering the first-pixel predictor and wraparound;
    // these pin the scalar contract in every configuration, including builds
    // where no accelerated kernels exist at all.
    {
        const uint8_t row[] = {0, 1, 2, 255};
        const uint8_t residuals[] = {0, 1, 1, 253};
        uint8_t out[sizeof(row)] = {};
        require(simd::scalar::left_filter_cost(row, sizeof(row)) == 5,
                "scalar filter cost known answer failed");
        simd::scalar::left_filter_emit(row, out, sizeof(row));
        require(std::equal(residuals, residuals + sizeof(row), out),
                "scalar filter emit known answer failed");
        for (size_t x = 1; x < sizeof(row); ++x)
            out[x] = static_cast<uint8_t>(out[x - 1] + out[x]);
        require(out[3] == 255, "scalar filter residuals did not invert");
    }
    {
        const uint8_t row[] = {250, 5};
        uint8_t out[2] = {};
        require(simd::scalar::left_filter_cost(row, sizeof(row)) == 17,
                "scalar wraparound cost known answer failed");
        simd::scalar::left_filter_emit(row, out, sizeof(row));
        require(out[0] == 250 && out[1] == 11,
                "scalar wraparound emit known answer failed");
        require(static_cast<uint8_t>(out[0] + out[1]) == 5,
                "scalar wraparound residuals did not invert");
    }
    {
        const uint8_t row[] = {200};
        require(simd::scalar::left_filter_cost(row, sizeof(row)) == 56,
                "single-pixel scalar cost known answer failed");
    }
}

void test_dispatch_selects_compiled_backends() {
    std::mt19937 rng(13572468);
    constexpr size_t width = 300;  // spans both vector widths plus scalar tails
    std::vector<uint8_t> row(width), expected(width), actual(width);
    for (uint8_t& byte : row) byte = static_cast<uint8_t>(rng());

    simd::scalar::left_filter_emit(row.data(), expected.data(), width);
    simd::left_filter_emit(row.data(), actual.data(), width);
    const uint64_t expected_cost = simd::scalar::left_filter_cost(row.data(), width);
    const uint64_t actual_cost = simd::left_filter_cost(row.data(), width);
    require(actual == expected && actual_cost == expected_cost,
            "dispatch diverged from the scalar reference");

#if defined(WIMF_NEON)
    std::vector<uint8_t> neon(width);
    simd::neon::left_filter_emit(row.data(), neon.data(), width);
    require(actual == neon && actual_cost == simd::neon::left_filter_cost(row.data(), width),
            "dispatch did not select the always-on NEON kernels");
#endif

#if defined(WIMF_AVX2_KERNELS)
    if (simd::has_avx2()) {
        std::vector<uint8_t> avx2(width);
        simd::avx2::left_filter_emit(row.data(), avx2.data(), width);
        require(actual == avx2 && actual_cost == simd::avx2::left_filter_cost(row.data(), width),
                "dispatch did not select the AVX2 kernels on an AVX2-capable host");
    }
#endif
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
        test_scalar_reference_known_answers();
        test_crc32_vectors();
        test_crc32_bulk_consistency();
        test_left_filter_kernels_match_scalar();
        test_dispatch_selects_compiled_backends();
        test_runtime_probes_report_compiled_backends();
        std::cout << "Backends: avx2=" << (simd::has_avx2() ? "on" : "off")
                  << " hardware_crc32=" << (simd::has_hardware_crc32() ? "on" : "off") << '\n';
        std::cout << "All native WIMF v2 SIMD tests passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Native SIMD test failure: " << error.what() << '\n';
        return 1;
    }
}
