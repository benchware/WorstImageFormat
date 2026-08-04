#include "wimf_c.h"

#include <assert.h>
#include <string.h>

int main(void) {
    uint8_t pixels[8 * 8 * 3];
    memset(pixels, 42, sizeof(pixels));
    wimf_image_view image = {pixels, 8, 8, 3, 1, 8 * 3};
    wimf_encode_options encode_options;
    wimf_encode_options_init(&encode_options);
    encode_options.lossless = 1;
    encode_options.synchronous = 1;
    encode_options.metadata_json = "{\"suite\":\"c-api\"}";
    encode_options.metadata_size = strlen(encode_options.metadata_json);
    wimf_buffer encoded = {0};
    wimf_status status = wimf_encode(&image, &encode_options, &encoded);
    assert(status.code == WIMF_STATUS_OK && encoded.size > 4);
    assert(memcmp(encoded.data, "WIM2", 4) == 0);

    wimf_decode_options decode_options;
    wimf_decode_options_init(&decode_options);
    decode_options.synchronous = 1;
    wimf_decoded_image decoded = {0};
    status = wimf_decode(encoded.data, encoded.size, &decode_options, &decoded);
    assert(status.code == WIMF_STATUS_OK);
    assert(decoded.width == 8 && decoded.height == 8 && decoded.channels == 3);
    assert(decoded.pixels.size == sizeof(pixels));
    assert(memcmp(decoded.pixels.data, pixels, sizeof(pixels)) == 0);
    assert(decoded.metadata_json.size == encode_options.metadata_size);
    assert(memcmp(decoded.metadata_json.data, encode_options.metadata_json, decoded.metadata_json.size) == 0);
    assert(decoded.stats.raw_tiles + decoded.stats.predictive_tiles + decoded.stats.palette_tiles +
               decoded.stats.wavelet_tiles == 1);
    wimf_decoded_image_free(&decoded);
    wimf_buffer_free(&encoded);
    assert(wimf_abi_version() == WIMF_C_ABI_VERSION);
    assert(strcmp(wimf_codec_version(), "2.2") == 0);

    uint16_t high_depth[17 * 17];
    for (size_t index = 0; index < 17 * 17; ++index) high_depth[index] = (uint16_t)(index * 197u);
    wimf_image_view high_view = {(const uint8_t*)high_depth, 17, 17, 1, 2, 17 * sizeof(uint16_t)};
    wimf_encode_options_init(&encode_options);
    encode_options.bit_depth = 16;
    encode_options.lossless = 1;
    encode_options.synchronous = 1;
    status = wimf_encode(&high_view, &encode_options, &encoded);
    assert(status.code == WIMF_STATUS_OK);

    wimf_decode_options_init(&decode_options);
    decode_options.use_roi = 1;
    decode_options.roi_x = 5;
    decode_options.roi_y = 6;
    decode_options.roi_width = 3;
    decode_options.roi_height = 4;
    decode_options.synchronous = 1;
    status = wimf_decode(encoded.data, encoded.size, &decode_options, &decoded);
    assert(status.code == WIMF_STATUS_OK && decoded.width == 3 && decoded.height == 4);
    assert(decoded.bit_depth == 16 && decoded.channels == 1 && decoded.pixels.size == 3 * 4 * 2);
    for (uint32_t row = 0; row < 4; ++row) {
        const uint16_t* actual = (const uint16_t*)decoded.pixels.data + row * 3;
        const uint16_t* expected = high_depth + (6 + row) * 17 + 5;
        assert(memcmp(actual, expected, 3 * sizeof(uint16_t)) == 0);
    }
    wimf_decoded_image_free(&decoded);
    wimf_buffer_free(&encoded);
    return 0;
}
