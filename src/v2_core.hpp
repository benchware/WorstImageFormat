#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace wimf::v2 {

enum class TileMode : uint8_t { Raw = 0, Predictive = 1, Palette = 2, Wavelet = 3 };

struct ImageView {
    const uint8_t* data;
    uint32_t width;
    uint32_t height;
    uint8_t channels;
    uint8_t bytes_per_sample;
    size_t row_stride;
};

struct RuntimeInfo {
    std::string architecture;
    std::string simd;
    unsigned hardware_threads;
};

struct TileRecord {
    uint16_t x;
    uint16_t y;
    uint16_t width;
    uint16_t height;
    uint8_t mode;
    uint8_t entropy;
    uint8_t layers;
    uint64_t offset;
    uint32_t size;
    uint32_t raw_size;
    uint32_t checksum;
    std::vector<uint8_t> payload;
};

struct ContainerInfo {
    uint8_t flags;
    uint8_t bit_depth;
    uint8_t channels;
    uint32_t width;
    uint32_t height;
    uint16_t tile_size;
    std::string metadata;
    std::vector<TileRecord> tiles;
};

RuntimeInfo runtime_info();
TileMode classify_tile(const ImageView& image);
std::vector<uint8_t> encode_predictive(const ImageView& image);
std::vector<uint8_t> decode_predictive(const uint8_t* data, size_t size, uint32_t width,
                                       uint32_t height, uint8_t channels, uint8_t bytes_per_sample);
std::vector<uint8_t> encode_palette(const ImageView& image);
std::vector<uint8_t> decode_palette(const uint8_t* data, size_t size, uint32_t width,
                                    uint32_t height, uint8_t channels, uint8_t bytes_per_sample);
std::vector<int64_t> wavelet_forward(const uint8_t* data, uint32_t width, uint32_t height,
                                     uint8_t bytes_per_sample, bool reversible, unsigned levels, double quantizer);
std::vector<uint8_t> wavelet_inverse(const int64_t* coefficients, size_t count, uint32_t width,
                                     uint32_t height, uint8_t bytes_per_sample, bool reversible,
                                     unsigned levels, double quantizer);
uint32_t crc32(const uint8_t* data, size_t size);
ContainerInfo parse_container(const uint8_t* data, size_t size);
std::vector<uint8_t> write_container(const ContainerInfo& container);

}  // namespace wimf::v2
