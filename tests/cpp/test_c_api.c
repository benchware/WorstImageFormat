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
    wimf_decoded_image_free(&decoded);
    wimf_buffer_free(&encoded);
    assert(wimf_abi_version() == WIMF_C_ABI_VERSION);
    return 0;
}
