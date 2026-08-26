// WIMF 3.0 (oxygen) container: quadtree tiling, CRC32C payloads, WIM2
// coexistence. Phase 1 implements the container, the split tree, and
// lossless Raw / Predictive-RC tile modes on top of the shared v2 codec
// primitives. Embedded zerotree wavelet streams, HDR sample formats, and
// perceptual quantization are later phases tracked in docs/wim3-format.md.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "v2_core.hpp"

namespace wimf::v3 {

using wimf::v2::DecodeResult;
using wimf::v2::ImageView;
using wimf::v2::Status;

constexpr uint8_t kDepthU8 = 0;    // phase 1
constexpr uint8_t kDepthU10 = 1;   // reserved, rejected
constexpr uint8_t kDepthU12 = 2;   // reserved, rejected
constexpr uint8_t kDepthU16 = 3;   // reserved, rejected
constexpr uint8_t kDepthF16 = 4;   // reserved, rejected

constexpr uint8_t kModeRaw = 0;
constexpr uint8_t kModePredictive = 1;

constexpr uint8_t kEntropyNone = 0;
constexpr uint8_t kEntropyRC = 2;  // predictive residuals through the range coder

struct ContainerInfo {
    uint32_t width = 0;
    uint32_t height = 0;
    uint8_t depth = kDepthU8;
    uint8_t channels = 0;
    uint16_t max_tile = 0;
    std::string metadata;
    struct Tile {
        uint32_t x = 0, y = 0, width = 0, height = 0;
        uint8_t mode = 0;
        uint8_t entropy = 0;
        uint64_t offset = 0;
        uint64_t packed_size = 0;
        uint32_t crc = 0;
    };
    std::vector<Tile> tiles;
};

struct EncodeOptionsV3 {
    uint16_t max_tile = 256;  // 16..4096; leaves never exceed this edge
    std::string metadata;
};

struct DecodeOptionsV3 {
    uint64_t max_output_bytes = 1024ull * 1024ull * 1024ull;
};

// Parses and fully validates a WIM3 container: magic, header fields, split
// tree coverage (exact tiling, leaf count), per-record geometry against the
// tree, payload bounds, non-overlap, and total length. Throws on any defect.
ContainerInfo parse_container(const uint8_t* data, size_t size);

uint32_t crc32c(const uint8_t* data, size_t size);

Status encode_image(const ImageView& image, const EncodeOptionsV3& options,
                    std::vector<uint8_t>& encoded) noexcept;

Status decode_image(const uint8_t* data, size_t size, const DecodeOptionsV3& options,
                    DecodeResult& decoded) noexcept;

}  // namespace wimf::v3
