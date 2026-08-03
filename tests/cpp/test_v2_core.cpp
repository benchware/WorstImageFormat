#include "v2_core.hpp"

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

using wimf::v2::ImageView;

namespace {

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

ImageView view(const std::vector<uint8_t>& pixels, uint32_t width, uint32_t height,
               uint8_t channels, uint8_t bytes_per_sample = 1) {
    return {pixels.data(), width, height, channels, bytes_per_sample,
            static_cast<size_t>(width) * channels * bytes_per_sample};
}

void test_predictive_roundtrip() {
    constexpr uint32_t width = 37, height = 29;
    constexpr uint8_t channels = 4;
    std::vector<uint8_t> pixels(width * height * channels);
    for (size_t i = 0; i < pixels.size(); ++i) pixels[i] = static_cast<uint8_t>((i * 31 + i / 7) & 255);
    const auto encoded = wimf::v2::encode_predictive(view(pixels, width, height, channels));
    const auto decoded = wimf::v2::decode_predictive(encoded.data(), encoded.size(), width, height, channels, 1);
    require(decoded == pixels, "8-bit predictive roundtrip failed");
}

void test_predictive_16bit_roundtrip() {
    constexpr uint32_t width = 19, height = 23;
    constexpr uint8_t channels = 3;
    std::vector<uint8_t> pixels(width * height * channels * 2);
    for (size_t i = 0; i < pixels.size() / 2; ++i) {
        const uint16_t value = static_cast<uint16_t>((i * 997) & 65535);
        pixels[i * 2] = static_cast<uint8_t>(value);
        pixels[i * 2 + 1] = static_cast<uint8_t>(value >> 8);
    }
    const auto encoded = wimf::v2::encode_predictive(view(pixels, width, height, channels, 2));
    const auto decoded = wimf::v2::decode_predictive(encoded.data(), encoded.size(), width, height, channels, 2);
    require(decoded == pixels, "16-bit predictive roundtrip failed");
}

void test_palette_roundtrip() {
    constexpr uint32_t width = 41, height = 17;
    constexpr uint8_t channels = 3;
    std::vector<uint8_t> pixels(width * height * channels);
    const uint8_t colors[4][3] = {{0, 0, 0}, {255, 255, 255}, {240, 20, 30}, {10, 80, 220}};
    for (size_t i = 0; i < width * height; ++i)
        std::copy(colors[i % 4], colors[i % 4] + channels, pixels.begin() + i * channels);
    const auto encoded = wimf::v2::encode_palette(view(pixels, width, height, channels));
    require(!encoded.empty(), "palette encoder rejected a four-color image");
    const auto decoded = wimf::v2::decode_palette(encoded.data(), encoded.size(), width, height, channels, 1);
    require(decoded == pixels, "palette roundtrip failed");
}

void test_reversible_wavelet() {
    constexpr uint32_t width = 32, height = 32;
    std::vector<uint8_t> pixels(width * height);
    for (size_t i = 0; i < pixels.size(); ++i) pixels[i] = static_cast<uint8_t>((i * 13 + i / width) & 255);
    const auto coefficients = wimf::v2::wavelet_forward(pixels.data(), width, height, 1, true, 3, 1.0);
    const auto decoded = wimf::v2::wavelet_inverse(coefficients.data(), coefficients.size(), width, height, 1, true, 3, 1.0);
    require(decoded == pixels, "CDF 5/3 roundtrip failed");
}

void test_crc_and_rejection() {
    const std::vector<uint8_t> value{'1', '2', '3', '4', '5', '6', '7', '8', '9'};
    require(wimf::v2::crc32(value.data(), value.size()) == 0xcbf43926u, "CRC32 reference vector failed");
    bool rejected = false;
    try {
        wimf::v2::decode_predictive(value.data(), value.size(), 100, 100, 3, 1);
    } catch (const std::exception&) {
        rejected = true;
    }
    require(rejected, "malformed predictive stream was accepted");
}

}  // namespace

int main() {
    try {
        test_predictive_roundtrip();
        test_predictive_16bit_roundtrip();
        test_palette_roundtrip();
        test_reversible_wavelet();
        test_crc_and_rejection();
        std::cout << "All native WIMF v2 tests passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Native test failure: " << error.what() << '\n';
        return 1;
    }
}
