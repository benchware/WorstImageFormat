// WIMF 3.0 (oxygen) container implementation. See v3_core.hpp for scope.
// Validation philosophy matches v2: every structural field is checked before
// any pixel work, payloads are checksummed with CRC32C, and hostile input
// fails with an exception instead of out-of-bounds access.

#include "v3_core.hpp"

#include <algorithm>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace wimf::v3 {
namespace {

constexpr size_t kHeaderSize = 38;
constexpr size_t kRecordSize = 40;
constexpr uint32_t kMaxTiles = 1u << 22;

uint16_t read16(const uint8_t* p) { return static_cast<uint16_t>(p[0] | p[1] << 8); }
uint32_t read32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) | static_cast<uint32_t>(p[1]) << 8 |
           static_cast<uint32_t>(p[2]) << 16 | static_cast<uint32_t>(p[3]) << 24;
}
uint64_t read64(const uint8_t* p) {
    uint64_t value = 0;
    for (int i = 7; i >= 0; --i) value = (value << 8) | p[i];
    return value;
}
void put16(std::vector<uint8_t>& out, uint16_t value) {
    out.push_back(static_cast<uint8_t>(value));
    out.push_back(static_cast<uint8_t>(value >> 8));
}
void put32(std::vector<uint8_t>& out, uint32_t value) {
    for (int i = 0; i < 4; ++i) out.push_back(static_cast<uint8_t>(value >> (i * 8)));
}
void put64(std::vector<uint8_t>& out, uint64_t value) {
    for (int i = 0; i < 8; ++i) out.push_back(static_cast<uint8_t>(value >> (i * 8)));
}

// CRC-32C (Castagnoli 0x1EDC6F41 reflected), table-driven.
uint32_t crc32c_impl(const uint8_t* data, size_t size) {
    static uint32_t table[256];
    static bool init = [] {
        for (uint32_t i = 0; i < 256; ++i) {
            uint32_t c = i;
            for (int k = 0; k < 8; ++k) c = c & 1 ? 0x82F63B78u ^ (c >> 1) : c >> 1;
            table[i] = c;
        }
        return true;
    }();
    (void)init;
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < size; ++i) crc = table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFu;
}

struct Node {
    uint32_t x, y, w, h;
};

// Split-tree node tags: 0 leaf, 1 vertical split (left/right halves),
// 2 horizontal split (top/bottom halves), 3 quad split. A dimension only
// splits when it exceeds max_tile, so narrow images never produce degenerate
// children. Writer and reader implement this exact rule.
void build_leaves(std::vector<Node>& leaves, std::vector<uint8_t>& tree, uint32_t x, uint32_t y,
                  uint32_t w, uint32_t h, uint32_t max_tile) {
    const bool split_w = w > max_tile, split_h = h > max_tile;
    if (!split_w && !split_h) {
        tree.push_back(0);
        leaves.push_back({x, y, w, h});
        return;
    }
    if (split_w && !split_h) {
        tree.push_back(1);
        const uint32_t w1 = w / 2;
        build_leaves(leaves, tree, x, y, w1, h, max_tile);
        build_leaves(leaves, tree, x + w1, y, w - w1, h, max_tile);
        return;
    }
    if (!split_w && split_h) {
        tree.push_back(2);
        const uint32_t h1 = h / 2;
        build_leaves(leaves, tree, x, y, w, h1, max_tile);
        build_leaves(leaves, tree, x, y + h1, w, h - h1, max_tile);
        return;
    }
    tree.push_back(3);
    const uint32_t w1 = w / 2, h1 = h / 2;
    build_leaves(leaves, tree, x, y, w1, h1, max_tile);
    build_leaves(leaves, tree, x + w1, y, w - w1, h1, max_tile);
    build_leaves(leaves, tree, x, y + h1, w1, h - h1, max_tile);
    build_leaves(leaves, tree, x + w1, y + h1, w - w1, h - h1, max_tile);
}

// Walks a serialized tree, reconstructing leaf rects under the same tagged
// split rule the writer used. Enforces exact tiling and that the leaf count
// matches `expected` exactly. Returns false on any defect.
bool walk_tree(const uint8_t* tree, size_t tree_len, size_t& pos, uint32_t x, uint32_t y,
               uint32_t w, uint32_t h, uint32_t max_tile, std::vector<Node>& leaves,
               size_t expected) {
    if (pos >= tree_len || leaves.size() > expected) return false;
    const uint8_t tag = tree[pos++];
    if (w == 0 || h == 0 || w > 0x10000u * 4u || h > 0x10000u * 4u) return false;
    if (tag == 0) {
        if (leaves.size() == expected) return false;  // more leaves than records
        leaves.push_back({x, y, w, h});
        return true;
    }
    if (tag == 1) {
        if (w < 2) return false;
        const uint32_t w1 = w / 2;
        return walk_tree(tree, tree_len, pos, x, y, w1, h, max_tile, leaves, expected) &&
               walk_tree(tree, tree_len, pos, x + w1, y, w - w1, h, max_tile, leaves, expected);
    }
    if (tag == 2) {
        if (h < 2) return false;
        const uint32_t h1 = h / 2;
        return walk_tree(tree, tree_len, pos, x, y, w, h1, max_tile, leaves, expected) &&
               walk_tree(tree, tree_len, pos, x, y + h1, w, h - h1, max_tile, leaves, expected);
    }
    if (tag != 3) return false;
    if (w < 2 || h < 2) return false;
    const uint32_t w1 = w / 2, h1 = h / 2;
    return walk_tree(tree, tree_len, pos, x, y, w1, h1, max_tile, leaves, expected) &&
           walk_tree(tree, tree_len, pos, x + w1, y, w - w1, h1, max_tile, leaves, expected) &&
           walk_tree(tree, tree_len, pos, x, y + h1, w1, h - h1, max_tile, leaves, expected) &&
           walk_tree(tree, tree_len, pos, x + w1, y + h1, w - w1, h - h1, max_tile, leaves,
                     expected);
}

ImageView subview(const ImageView& image, const Node& n) {
    return {image.data + static_cast<size_t>(n.y) * image.row_stride +
                static_cast<size_t>(n.x) * image.channels * image.bytes_per_sample,
            n.w, n.h, image.channels, image.bytes_per_sample, image.row_stride};
}

}  // namespace

uint32_t crc32c(const uint8_t* data, size_t size) { return crc32c_impl(data, size); }

ContainerInfo parse_container(const uint8_t* data, size_t size) {
    if (!data || size < kHeaderSize || std::memcmp(data, "WIM3", 4) != 0)
        throw std::runtime_error("not a supported WIM3 container");
    if (data[4] != 3) throw std::runtime_error("unsupported WIM3 version");
    ContainerInfo out{};
    out.depth = data[6];
    out.channels = data[7];
    out.width = read32(data + 8);
    out.height = read32(data + 12);
    out.max_tile = read16(data + 16);
    const uint32_t metadata_len = read32(data + 18);
    const uint32_t tree_len = read32(data + 22);
    const uint32_t tile_count = read32(data + 26);
    const uint64_t payload_len = read64(data + 30);
    if (!out.width || !out.height || !out.channels || out.channels > 16 ||
        out.depth > kDepthU16 || out.max_tile < 16 || out.max_tile > 4096)
        throw std::runtime_error("invalid WIM3 properties");
    const uint64_t index_start = kHeaderSize + metadata_len + tree_len;
    const uint64_t records_bytes = static_cast<uint64_t>(tile_count) * kRecordSize;
    if (tile_count > kMaxTiles || index_start > size || records_bytes > size - index_start)
        throw std::runtime_error("truncated WIM3 header or index");
    out.metadata.assign(reinterpret_cast<const char*>(data) + kHeaderSize, metadata_len);

    // Tree must reproduce the exact leaf tiling and the exact record count;
    // records are then validated against it one-to-one.
    std::vector<Node> leaves;
    leaves.reserve(tile_count);
    size_t tree_pos = 0;
    if (!walk_tree(data + kHeaderSize + metadata_len, tree_len, tree_pos, 0, 0, out.width,
                   out.height, out.max_tile, leaves, tile_count) ||
        tree_pos != tree_len || leaves.size() != tile_count)
        throw std::runtime_error("invalid WIM3 split tree");

    const uint64_t payload_start = index_start + records_bytes;
    uint64_t cursor = payload_start;
    for (uint32_t i = 0; i < tile_count; ++i) {
        const uint8_t* p = data + index_start + static_cast<size_t>(i) * kRecordSize;
        ContainerInfo::Tile tile{};
        tile.x = read32(p);
        tile.y = read32(p + 4);
        tile.width = read32(p + 8);
        tile.height = read32(p + 12);
        tile.mode = p[16];
        tile.entropy = p[17];
        // p[18] transform and p[19] quality map are reserved and must be zero in phase 1.
        if (p[18] != 0 || p[19] != 0) throw std::runtime_error("unknown WIM3 tile extension");
        tile.offset = read64(p + 20);
        tile.packed_size = read64(p + 28);
        tile.crc = read32(p + 36);
        const Node& leaf = leaves[i];
        if (tile.x != leaf.x || tile.y != leaf.y || tile.width != leaf.w || tile.height != leaf.h)
            throw std::runtime_error("WIM3 tile geometry disagrees with split tree");
        if (tile.mode > kModeWavelet) throw std::runtime_error("invalid WIM3 tile mode");
        if (tile.mode == kModeRaw && tile.entropy != kEntropyNone)
            throw std::runtime_error("raw tiles must be uncompressed");
        if (tile.mode == kModePredictive && tile.entropy != kEntropyRC)
            throw std::runtime_error("predictive tiles require range-coded entropy");
        if (tile.mode == kModeWavelet && tile.entropy != kEntropyNone)
            throw std::runtime_error("wavelet tiles must be uncompressed");
        if (tile.offset != cursor || tile.packed_size == 0 ||
            tile.packed_size > size - payload_start || tile.offset > size - tile.packed_size)
            throw std::runtime_error("invalid WIM3 tile entry");
        cursor += tile.packed_size;
        out.tiles.push_back(tile);
    }
    if (cursor - payload_start != payload_len || payload_start + payload_len != size)
        throw std::runtime_error("WIM3 payload length mismatch");
    return out;
}

Status encode_image(const ImageView& image, const EncodeOptionsV3& options,
                    std::vector<uint8_t>& encoded) noexcept {
    try {
        if (!image.data || !image.width || !image.height || !image.channels || image.channels > 16)
            throw std::runtime_error("unsupported image layout for WIM3");
        const uint8_t bps = options.depth == kDepthU8 ? 1 : 2;
        if (options.depth > kDepthU16 || image.bytes_per_sample != bps)
            throw std::runtime_error("depth enum disagrees with sample width");
        if (options.max_tile < 16 || options.max_tile > 4096)
            throw std::runtime_error("max_tile must be between 16 and 4096");
        if (options.quality < 1 || options.quality > 10)
            throw std::runtime_error("quality must be between 1 and 10");
        // Lossy coding quantizes wavelet coefficients by a power-of-two
        // shift derived from quality: quality 10 (or lossless) keeps every
        // bitplane, quality 1 discards up to nine.
        const uint8_t quant_shift =
            options.lossless ? 0 : static_cast<uint8_t>(std::clamp<int>(10 - options.quality, 0, 9));
        if (options.metadata.size() > 16u * 1024u * 1024u)
            throw std::runtime_error("metadata too large");

        std::vector<Node> leaves;
        std::vector<uint8_t> tree;
        build_leaves(leaves, tree, 0, 0, image.width, image.height, options.max_tile);

        struct Payload {
            uint8_t mode, entropy;
            uint32_t crc;
            std::vector<uint8_t> bytes;
        };
        std::vector<Payload> payloads;
        payloads.reserve(leaves.size());
        for (const Node& leaf : leaves) {
            const ImageView view = subview(image, leaf);
            auto rc = wimf::v2::encode_predictive_rc(view);
            const size_t raw_bytes =
                static_cast<size_t>(leaf.w) * leaf.h * image.channels * bps;
            struct Candidate {
                uint8_t mode, entropy;
                size_t size;
                std::vector<uint8_t> bytes;
            };
            Candidate best{0, kEntropyNone, 0, {}};
            // Raw candidate.
            {
                std::vector<uint8_t> raw(raw_bytes);
                for (uint32_t row = 0; row < leaf.h; ++row)
                    std::memcpy(raw.data() + static_cast<size_t>(row) * leaf.w * image.channels * bps,
                                view.data + static_cast<size_t>(row) * view.row_stride,
                                static_cast<size_t>(leaf.w) * image.channels * bps);
                best = {kModeRaw, kEntropyNone, raw.size(), std::move(raw)};
            }
            if (quant_shift == 0 && rc.size() < best.size)
                best = {kModePredictive, kEntropyRC, rc.size(), std::move(rc)};
            // The embedded wavelet candidate costs full bitplane coding, so it
            // only runs for leaves the classifier flags as smooth/photographic
            // - the same shortlist gating the v2 auto path uses. Lossy coding
            // always offers it: quantization can win on any content.
            if (quant_shift > 0 || wimf::v2::classify_tile(view) == wimf::v2::TileMode::Wavelet) {
                auto embedded = embedded::encode(view, quant_shift);
                if (embedded.size() < best.size)
                    best = {kModeWavelet, kEntropyNone, embedded.size(), std::move(embedded)};
            }
            payloads.push_back({best.mode, best.entropy,
                                crc32c(best.bytes.data(), best.bytes.size()),
                                std::move(best.bytes)});
        }

        uint64_t payload_total = 0;
        for (const auto& payload : payloads) payload_total += payload.bytes.size();

        std::vector<uint8_t> out;
        out.reserve(static_cast<size_t>(kHeaderSize) + options.metadata.size() + tree.size() +
                    payloads.size() * kRecordSize + static_cast<size_t>(payload_total));
        out.insert(out.end(), {'W', 'I', 'M', '3', 3, 0, options.depth, image.channels});
        put32(out, image.width);
        put32(out, image.height);
        put16(out, options.max_tile);
        put32(out, static_cast<uint32_t>(options.metadata.size()));
        put32(out, static_cast<uint32_t>(tree.size()));
        put32(out, static_cast<uint32_t>(payloads.size()));
        put64(out, payload_total);
        out.insert(out.end(), options.metadata.begin(), options.metadata.end());
        out.insert(out.end(), tree.begin(), tree.end());
        uint64_t offset = static_cast<uint64_t>(out.size()) +
                          static_cast<uint64_t>(payloads.size()) * kRecordSize;
        for (size_t i = 0; i < payloads.size(); ++i) {
            const Node& leaf = leaves[i];
            const auto& payload = payloads[i];
            put32(out, leaf.x);
            put32(out, leaf.y);
            put32(out, leaf.w);
            put32(out, leaf.h);
            out.push_back(payload.mode);
            out.push_back(payload.entropy);
            out.push_back(0);  // transform, reserved
            out.push_back(0);  // quality map, reserved
            put64(out, offset);
            put64(out, payload.bytes.size());
            put32(out, payload.crc);
            offset += payload.bytes.size();
        }
        for (const auto& payload : payloads) out.insert(out.end(), payload.bytes.begin(),
                                                        payload.bytes.end());
        encoded = std::move(out);
        return Status{};
    } catch (const std::exception& error) {
        return {wimf::v2::ErrorCode::InvalidArgument, error.what()};
    }
}

Status decode_image(const uint8_t* data, size_t size, const DecodeOptionsV3& options,
                    DecodeResult& decoded) noexcept {
    try {
        const ContainerInfo info = parse_container(data, size);
        const uint8_t bps = info.depth == kDepthU8 ? 1 : 2;
        const size_t pixel_bytes =
            static_cast<size_t>(info.width) * info.height * info.channels * bps;
        if (pixel_bytes > options.max_output_bytes)
            return {wimf::v2::ErrorCode::ResourceLimit, "output exceeds limit"};
        decoded = DecodeResult{};
        decoded.pixels.assign(pixel_bytes, 0);
        decoded.width = info.width;
        decoded.height = info.height;
        decoded.channels = info.channels;
        decoded.bit_depth = bps == 1 ? 8 : 16;
        decoded.metadata = info.metadata;

        for (const auto& tile : info.tiles) {
            const uint8_t* packed = data + tile.offset;
            if (crc32c(packed, static_cast<size_t>(tile.packed_size)) != tile.crc)
                throw std::runtime_error("WIM3 tile checksum mismatch");
            std::vector<uint8_t> pixels;
            if (tile.mode == kModeRaw) {
                pixels.assign(packed, packed + tile.packed_size);
                const size_t expected =
                    static_cast<size_t>(tile.width) * tile.height * info.channels * bps;
                if (pixels.size() != expected)
                    throw std::runtime_error("invalid raw tile length");
            } else if (tile.mode == kModePredictive) {
                // Two stages, mirroring v2: range-coded stream -> classic
                // predictive payload -> reconstructed interleaved pixels.
                const auto classic =
                    wimf::v2::decode_predictive_rc(packed, static_cast<size_t>(tile.packed_size),
                                                   tile.width, tile.height, info.channels, bps);
                pixels = wimf::v2::decode_predictive(classic.data(), classic.size(), tile.width,
                                                     tile.height, info.channels, bps);
            } else {
                pixels = embedded::decode(packed, static_cast<size_t>(tile.packed_size),
                                          tile.width, tile.height, info.channels, bps,
                                          options.target_planes);
            }
            const size_t row_bytes =
                static_cast<size_t>(tile.width) * info.channels * bps;
            for (uint32_t row = 0; row < tile.height; ++row) {
                const size_t source = static_cast<size_t>(row) * row_bytes;
                const size_t target =
                    (static_cast<size_t>(tile.y + row) * info.width + tile.x) * info.channels * bps;
                std::memcpy(decoded.pixels.data() + target, pixels.data() + source, row_bytes);
            }
        }
        return Status{};
    } catch (const std::exception& error) {
        return {wimf::v2::ErrorCode::CorruptData, error.what()};
    }
}

}  // namespace wimf::v3
