#include "wimf_c.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "v2_core.hpp"

namespace {
wimf_status status_from(const wimf::v2::Status& source) {
    wimf_status result{};
    result.code = static_cast<wimf_status_code>(source.code);
    const size_t length = std::min(source.message.size(), sizeof(result.message) - 1);
    std::memcpy(result.message, source.message.data(), length);
    result.message[length] = '\0';
    return result;
}

wimf_status failure(wimf_status_code code, const char* message) {
    wimf_status result{};
    result.code = code;
    std::strncpy(result.message, message, sizeof(result.message) - 1);
    return result;
}

wimf_status invalid(const char* message) { return failure(WIMF_STATUS_INVALID_ARGUMENT, message); }

bool copy_buffer(const std::vector<uint8_t>& source, wimf_buffer* output) {
    output->data = nullptr;
    output->size = 0;
    if (source.empty()) return true;
    auto* memory = static_cast<uint8_t*>(std::malloc(source.size()));
    if (!memory) return false;
    std::memcpy(memory, source.data(), source.size());
    output->data = memory;
    output->size = source.size();
    return true;
}
}  // namespace

extern "C" uint32_t wimf_abi_version(void) { return WIMF_C_ABI_VERSION; }

extern "C" void wimf_encode_options_init(wimf_encode_options* options) {
    if (!options) return;
    *options = {};
    options->struct_size = sizeof(*options);
    options->bit_depth = 8;
    options->quality = 7;
    options->preset = 1;
    options->tile_size = 128;
}

extern "C" void wimf_decode_options_init(wimf_decode_options* options) {
    if (!options) return;
    *options = {};
    options->struct_size = sizeof(*options);
    options->target_layer = 2;
    options->max_output_bytes = 1024ull * 1024ull * 1024ull;
}

extern "C" wimf_status wimf_encode(const wimf_image_view* image, const wimf_encode_options* options,
                                     wimf_buffer* output) {
    if (!image || !options || !output) return invalid("null encode argument");
    if (options->struct_size != sizeof(*options)) return invalid("unsupported encode options size");
    *output = {};
    wimf::v2::ImageView view{image->data, image->width, image->height, image->channels,
                             image->bytes_per_sample, image->row_stride};
    wimf::v2::EncodeOptions native;
    native.bit_depth = options->bit_depth;
    native.quality = options->quality;
    native.lossless = options->lossless != 0;
    native.preset = static_cast<wimf::v2::SearchPreset>(options->preset);
    native.codec = static_cast<wimf::v2::CodecMode>(options->codec);
    native.tile_size = options->tile_size;
    native.threads = options->threads;
    native.execution = options->synchronous ? wimf::v2::ExecutionPolicy::Synchronous
                                             : wimf::v2::ExecutionPolicy::Threaded;
    if (options->metadata_json && options->metadata_size)
        native.metadata.assign(options->metadata_json, options->metadata_size);
    std::vector<uint8_t> encoded;
    const auto status = wimf::v2::encode_image(view, native, encoded);
    if (!status) return status_from(status);
    if (!copy_buffer(encoded, output)) return failure(WIMF_STATUS_RESOURCE_LIMIT, "output allocation failed");
    return {};
}

extern "C" wimf_status wimf_decode(const uint8_t* data, size_t size, const wimf_decode_options* options,
                                     wimf_decoded_image* output) {
    if (!data || !options || !output) return invalid("null decode argument");
    if (options->struct_size != sizeof(*options)) return invalid("unsupported decode options size");
    *output = {};
    wimf::v2::DecodeOptions native;
    native.use_roi = options->use_roi != 0;
    native.roi_x = options->roi_x; native.roi_y = options->roi_y;
    native.roi_width = options->roi_width; native.roi_height = options->roi_height;
    native.target_layer = options->target_layer;
    native.threads = options->threads;
    native.execution = options->synchronous ? wimf::v2::ExecutionPolicy::Synchronous
                                             : wimf::v2::ExecutionPolicy::Threaded;
    native.max_output_bytes = options->max_output_bytes;
    wimf::v2::DecodeResult decoded;
    const auto status = wimf::v2::decode_image(data, size, native, decoded);
    if (!status) return status_from(status);
    if (!copy_buffer(decoded.pixels, &output->pixels))
        return failure(WIMF_STATUS_RESOURCE_LIMIT, "output allocation failed");
    output->width = decoded.width; output->height = decoded.height;
    output->channels = decoded.channels; output->bit_depth = decoded.bit_depth;
    return {};
}

extern "C" void wimf_buffer_free(wimf_buffer* buffer) {
    if (!buffer) return;
    std::free(buffer->data);
    *buffer = {};
}

extern "C" void wimf_decoded_image_free(wimf_decoded_image* image) {
    if (!image) return;
    wimf_buffer_free(&image->pixels);
    image->width = image->height = 0;
    image->channels = image->bit_depth = 0;
}
