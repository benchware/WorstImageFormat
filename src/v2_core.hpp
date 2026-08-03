#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace wimf::v2 {

enum class TileMode : uint8_t { Raw = 0, Predictive = 1, Palette = 2, Wavelet = 3 };
enum class CodecMode : uint8_t { Auto = 0, Raw = 1, Predictive = 2, Palette = 3, Wavelet = 4 };
enum class SearchPreset : uint8_t { Fast = 0, Balanced = 1, Extreme = 2 };
enum class ExecutionPolicy : uint8_t { Synchronous = 0, Threaded = 1 };
enum class ErrorCode : uint8_t { Ok = 0, InvalidArgument = 1, CorruptData = 2, ResourceLimit = 3, Internal = 4, Cancelled = 5 };

struct OperationControl {
    void* context = nullptr;
    bool (*is_cancelled)(void*) noexcept = nullptr;
    void (*on_progress)(void*, const char*, uint64_t, uint64_t) noexcept = nullptr;
};

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

struct Status {
    ErrorCode code = ErrorCode::Ok;
    std::string message;
    explicit operator bool() const { return code == ErrorCode::Ok; }
};

struct EncodeOptions {
    uint8_t bit_depth = 8;
    uint8_t quality = 7;
    bool lossless = false;
    SearchPreset preset = SearchPreset::Balanced;
    CodecMode codec = CodecMode::Auto;
    uint16_t tile_size = 128;
    unsigned threads = 0;
    ExecutionPolicy execution = ExecutionPolicy::Threaded;
    std::string metadata;
    const OperationControl* control = nullptr;
};

struct DecodeOptions {
    bool use_roi = false;
    uint32_t roi_x = 0;
    uint32_t roi_y = 0;
    uint32_t roi_width = 0;
    uint32_t roi_height = 0;
    uint8_t target_layer = 2;
    unsigned threads = 0;
    ExecutionPolicy execution = ExecutionPolicy::Threaded;
    uint64_t max_output_bytes = 1024ull * 1024ull * 1024ull;
    const OperationControl* control = nullptr;
};

struct CodecStats {
    uint32_t raw_tiles = 0;
    uint32_t predictive_tiles = 0;
    uint32_t palette_tiles = 0;
    uint32_t wavelet_tiles = 0;
    unsigned effective_threads = 1;
};

struct DecodeResult {
    std::vector<uint8_t> pixels;
    uint32_t width = 0;
    uint32_t height = 0;
    uint8_t channels = 0;
    uint8_t bit_depth = 0;
    std::string metadata;
    CodecStats stats;
};

struct CompareResult {
    std::vector<uint8_t> difference;
    double mse = 0;
    uint32_t maximum_error = 0;
    double psnr = 0;
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
Status encode_image(const ImageView& image, const EncodeOptions& options,
                    std::vector<uint8_t>& encoded, CodecStats* stats = nullptr) noexcept;
Status decode_image(const uint8_t* data, size_t size, const DecodeOptions& options,
                    DecodeResult& decoded) noexcept;
Status compare_images(const ImageView& first, const ImageView& second, uint8_t bit_depth,
                      CompareResult& compared) noexcept;
Status rewrite_metadata(const uint8_t* data, size_t size, const std::string& metadata,
                        std::vector<uint8_t>& rewritten) noexcept;

}  // namespace wimf::v2
