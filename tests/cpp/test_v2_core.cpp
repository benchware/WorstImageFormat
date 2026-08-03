#include "v2_core.hpp"

#include <algorithm>
#include <cstring>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

using wimf::v2::ImageView;

namespace {

struct TestControl {
    bool cancelled = false;
    uint64_t completed = 0;
    uint64_t total = 0;
};

bool is_cancelled(void* context) noexcept { return static_cast<TestControl*>(context)->cancelled; }
void on_progress(void* context, const char*, uint64_t completed, uint64_t total) noexcept {
    auto* control = static_cast<TestControl*>(context);
    control->completed = completed;
    control->total = total;
}

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

void test_container_roundtrip() {
    wimf::v2::ContainerInfo source{};
    source.flags = 1;
    source.bit_depth = 8;
    source.channels = 3;
    source.width = 17;
    source.height = 19;
    source.tile_size = 128;
    source.metadata = "{\"format_version\":2}";
    wimf::v2::TileRecord tile{};
    tile.width = 17;
    tile.height = 19;
    tile.mode = 0;
    tile.entropy = 0;
    tile.layers = 1;
    tile.raw_size = 17 * 19 * 3;
    tile.payload.resize(tile.raw_size, 42);
    source.tiles.push_back(tile);
    const auto encoded = wimf::v2::write_container(source);
    const auto decoded = wimf::v2::parse_container(encoded.data(), encoded.size());
    require(decoded.width == source.width && decoded.height == source.height, "container dimensions changed");
    require(decoded.tiles.size() == 1 && decoded.tiles[0].mode == 0, "container tile index changed");
    require(decoded.tiles[0].checksum == wimf::v2::crc32(tile.payload.data(), tile.payload.size()), "container checksum changed");
}

void test_image_pipeline() {
    constexpr uint32_t width = 259, height = 133;
    constexpr uint8_t channels = 3;
    std::vector<uint8_t> pixels(width * height * channels);
    for (uint32_t y = 0; y < height; ++y)
        for (uint32_t x = 0; x < width; ++x)
            for (uint8_t channel = 0; channel < channels; ++channel)
                pixels[(static_cast<size_t>(y) * width + x) * channels + channel] =
                    static_cast<uint8_t>((x * 3 + y * 5 + channel * 71) & 255);

    wimf::v2::EncodeOptions synchronous{};
    synchronous.lossless = true;
    synchronous.codec = wimf::v2::CodecMode::Predictive;
    synchronous.execution = wimf::v2::ExecutionPolicy::Synchronous;
    synchronous.metadata = "{\"native\":true}";
    std::vector<uint8_t> encoded_sync;
    wimf::v2::CodecStats sync_stats;
    require(static_cast<bool>(wimf::v2::encode_image(view(pixels, width, height, channels), synchronous,
                                                     encoded_sync, &sync_stats)),
            "synchronous image encode failed");

    for (const unsigned threads : {1u, 2u, 4u, 0u}) {
        auto threaded = synchronous;
        threaded.execution = wimf::v2::ExecutionPolicy::Threaded;
        threaded.threads = threads;
        std::vector<uint8_t> encoded_threaded;
        require(static_cast<bool>(wimf::v2::encode_image(view(pixels, width, height, channels), threaded,
                                                         encoded_threaded)),
                "threaded image encode failed");
        require(encoded_sync == encoded_threaded, "thread count changed encoded output");
    }
    require(sync_stats.predictive_tiles == 6, "unexpected native tile statistics");

    TestControl progress{};
    wimf::v2::OperationControl operation{&progress, is_cancelled, on_progress};
    auto observed = synchronous;
    observed.control = &operation;
    std::vector<uint8_t> observed_output;
    require(static_cast<bool>(wimf::v2::encode_image(view(pixels, width, height, channels), observed,
                                                     observed_output)),
            "observed image encode failed");
    require(progress.completed == 6 && progress.total == 6, "native progress callback was incomplete");
    progress.cancelled = true;
    const auto cancelled = wimf::v2::encode_image(view(pixels, width, height, channels), observed, observed_output);
    require(!cancelled && cancelled.code == wimf::v2::ErrorCode::Cancelled,
            "native encode ignored cancellation");

    wimf::v2::DecodeResult decoded;
    require(static_cast<bool>(wimf::v2::decode_image(encoded_sync.data(), encoded_sync.size(), {}, decoded)),
            "image decode failed");
    require(decoded.pixels == pixels, "native image roundtrip changed pixels");
    require(decoded.metadata == synchronous.metadata, "native metadata changed");

    wimf::v2::DecodeOptions limited{};
    limited.max_output_bytes = pixels.size() - 1;
    const auto limited_status = wimf::v2::decode_image(encoded_sync.data(), encoded_sync.size(), limited, decoded);
    require(!limited_status && limited_status.code == wimf::v2::ErrorCode::ResourceLimit,
            "native image decoder ignored output allocation limit");

    wimf::v2::DecodeOptions roi{};
    roi.use_roi = true;
    roi.roi_x = 117;
    roi.roi_y = 61;
    roi.roi_width = 91;
    roi.roi_height = 49;
    roi.execution = wimf::v2::ExecutionPolicy::Synchronous;
    wimf::v2::DecodeResult region;
    require(static_cast<bool>(wimf::v2::decode_image(encoded_sync.data(), encoded_sync.size(), roi, region)),
            "native ROI decode failed");
    require(region.width == roi.roi_width && region.height == roi.roi_height,
            "native ROI dimensions changed");
    for (uint32_t y = 0; y < roi.roi_height; ++y)
        for (uint32_t x = 0; x < roi.roi_width; ++x)
            for (uint8_t channel = 0; channel < channels; ++channel)
                require(region.pixels[(static_cast<size_t>(y) * roi.roi_width + x) * channels + channel] ==
                            pixels[(static_cast<size_t>(y + roi.roi_y) * width + x + roi.roi_x) * channels + channel],
                        "native ROI pixels changed");

    auto corrupt = encoded_sync;
    corrupt.back() ^= 0x80;
    require(!wimf::v2::decode_image(corrupt.data(), corrupt.size(), {}, decoded),
            "native image decoder accepted corruption");

    for (const auto mode : {wimf::v2::CodecMode::Raw, wimf::v2::CodecMode::Predictive,
                            wimf::v2::CodecMode::Wavelet}) {
        auto forced_options = synchronous;
        forced_options.codec = mode;
        std::vector<uint8_t> forced;
        require(static_cast<bool>(wimf::v2::encode_image(view(pixels, width, height, channels), forced_options,
                                                         forced)),
                "forced mode encode failed");
        require(static_cast<bool>(wimf::v2::decode_image(forced.data(), forced.size(), {}, decoded)),
                "forced mode decode failed");
        require(decoded.pixels == pixels, "forced lossless mode changed pixels");
    }

    std::vector<uint8_t> palette_pixels(32 * 35 * 3);
    const uint8_t colors[4][3] = {{0, 0, 0}, {255, 255, 255}, {220, 30, 80}, {20, 90, 230}};
    for (size_t i = 0; i < 32 * 35; ++i)
        std::memcpy(palette_pixels.data() + i * 3, colors[(i * 17 + i / 11) % 4], 3);
    const wimf::v2::ImageView palette_view{palette_pixels.data(), 35, 32, 3, 1, 35 * 3};
    auto palette_options = synchronous;
    palette_options.codec = wimf::v2::CodecMode::Palette;
    std::vector<uint8_t> palette_encoded;
    require(static_cast<bool>(wimf::v2::encode_image(palette_view, palette_options, palette_encoded)),
            "palette image encode failed");
    require(static_cast<bool>(wimf::v2::decode_image(palette_encoded.data(), palette_encoded.size(), {}, decoded)),
            "palette image decode failed");
    require(decoded.pixels == palette_pixels, "palette mode changed pixels");

    constexpr uint32_t high_width = 67, high_height = 39;
    std::vector<uint8_t> high_pixels(high_width * high_height * 2 * 2);
    for (size_t i = 0; i < high_pixels.size() / 2; ++i) {
        const uint16_t value = static_cast<uint16_t>((i * 619 + i / 13) & 1023);
        high_pixels[i * 2] = static_cast<uint8_t>(value);
        high_pixels[i * 2 + 1] = static_cast<uint8_t>(value >> 8);
    }
    auto high_options = synchronous;
    high_options.bit_depth = 10;
    high_options.codec = wimf::v2::CodecMode::Predictive;
    std::vector<uint8_t> high_encoded;
    require(static_cast<bool>(wimf::v2::encode_image(view(high_pixels, high_width, high_height, 2, 2),
                                                     high_options, high_encoded)),
            "10-bit image encode failed");
    require(static_cast<bool>(wimf::v2::decode_image(high_encoded.data(), high_encoded.size(), {}, decoded)),
            "10-bit image decode failed");
    require(decoded.bit_depth == 10 && decoded.pixels == high_pixels, "10-bit image roundtrip changed pixels");

    std::vector<uint8_t> changed = pixels;
    changed[17] = static_cast<uint8_t>(changed[17] + 3);
    wimf::v2::CompareResult comparison;
    require(static_cast<bool>(wimf::v2::compare_images(view(pixels, width, height, channels),
                                                       view(changed, width, height, channels), 8, comparison)),
            "native image comparison failed");
    require(comparison.maximum_error == 3 && comparison.mse > 0 && comparison.difference[17] == 3,
            "native image comparison returned incorrect metrics");

    std::vector<uint8_t> rewritten;
    require(static_cast<bool>(wimf::v2::rewrite_metadata(encoded_sync.data(), encoded_sync.size(),
                                                         "{\"edited\":true}", rewritten)),
            "native metadata rewrite failed");
    const auto before = wimf::v2::parse_container(encoded_sync.data(), encoded_sync.size());
    const auto after = wimf::v2::parse_container(rewritten.data(), rewritten.size());
    require(after.metadata == "{\"edited\":true}" && before.tiles.size() == after.tiles.size(),
            "native metadata rewrite changed container structure");
    for (size_t index = 0; index < before.tiles.size(); ++index)
        require(before.tiles[index].size == after.tiles[index].size &&
                    std::equal(encoded_sync.begin() + before.tiles[index].offset,
                               encoded_sync.begin() + before.tiles[index].offset + before.tiles[index].size,
                               rewritten.begin() + after.tiles[index].offset),
                "native metadata rewrite changed a tile payload");
}

}  // namespace

int main() {
    try {
        test_predictive_roundtrip();
        test_predictive_16bit_roundtrip();
        test_palette_roundtrip();
        test_reversible_wavelet();
        test_crc_and_rejection();
        test_container_roundtrip();
        test_image_pipeline();
        std::cout << "All native WIMF v2 tests passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Native test failure: " << error.what() << '\n';
        return 1;
    }
}
