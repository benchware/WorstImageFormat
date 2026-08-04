#ifndef WIMF_C_H
#define WIMF_C_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define WIMF_C_ABI_VERSION 1u

/* ABI v1 ownership summary:
 * - inputs are borrowed for the duration of a call;
 * - successful output buffers must be freed by this library;
 * - calls are independent and may execute concurrently;
 * - no C++ exception crosses this interface.
 * See docs/c-api.md for the complete contract. */

#if defined(_WIN32) && defined(WIMF_C_SHARED)
#  if defined(WIMF_C_BUILDING_DLL)
#    define WIMF_C_API __declspec(dllexport)
#  else
#    define WIMF_C_API __declspec(dllimport)
#  endif
#elif defined(__GNUC__) && defined(WIMF_C_BUILDING_DLL)
#  define WIMF_C_API __attribute__((visibility("default")))
#else
#  define WIMF_C_API
#endif

typedef enum wimf_status_code {
    WIMF_STATUS_OK = 0,
    WIMF_STATUS_INVALID_ARGUMENT = 1,
    WIMF_STATUS_CORRUPT_DATA = 2,
    WIMF_STATUS_RESOURCE_LIMIT = 3,
    WIMF_STATUS_INTERNAL = 4,
    WIMF_STATUS_CANCELLED = 5
} wimf_status_code;

typedef struct wimf_status {
    wimf_status_code code;
    char message[256];
} wimf_status;

typedef struct wimf_buffer {
    uint8_t* data;
    size_t size;
} wimf_buffer;

typedef struct wimf_image_view {
    const uint8_t* data;
    uint32_t width;
    uint32_t height;
    uint8_t channels;
    uint8_t bytes_per_sample;
    size_t row_stride;
} wimf_image_view;

typedef struct wimf_encode_options {
    uint32_t struct_size;
    uint8_t bit_depth;
    uint8_t quality;
    uint8_t lossless;
    uint8_t preset;
    uint8_t codec;
    uint16_t tile_size;
    uint32_t threads;
    uint8_t synchronous;
    const char* metadata_json;
    size_t metadata_size;
} wimf_encode_options;

typedef struct wimf_decode_options {
    uint32_t struct_size;
    uint8_t use_roi;
    uint32_t roi_x;
    uint32_t roi_y;
    uint32_t roi_width;
    uint32_t roi_height;
    uint8_t target_layer;
    uint32_t threads;
    uint8_t synchronous;
    uint64_t max_output_bytes;
} wimf_decode_options;

typedef struct wimf_codec_stats {
    uint32_t raw_tiles;
    uint32_t predictive_tiles;
    uint32_t palette_tiles;
    uint32_t wavelet_tiles;
    uint32_t effective_threads;
} wimf_codec_stats;

typedef struct wimf_decoded_image {
    wimf_buffer pixels;
    uint32_t width;
    uint32_t height;
    uint8_t channels;
    uint8_t bit_depth;
    wimf_buffer metadata_json;
    wimf_codec_stats stats;
} wimf_decoded_image;

WIMF_C_API uint32_t wimf_abi_version(void);
WIMF_C_API const char* wimf_codec_version(void);
WIMF_C_API void wimf_encode_options_init(wimf_encode_options* options);
WIMF_C_API void wimf_decode_options_init(wimf_decode_options* options);
WIMF_C_API wimf_status wimf_encode(const wimf_image_view* image, const wimf_encode_options* options,
                                   wimf_buffer* output);
WIMF_C_API wimf_status wimf_decode(const uint8_t* data, size_t size, const wimf_decode_options* options,
                                   wimf_decoded_image* output);
WIMF_C_API void wimf_buffer_free(wimf_buffer* buffer);
WIMF_C_API void wimf_decoded_image_free(wimf_decoded_image* image);

#ifdef __cplusplus
}
#endif
#endif
