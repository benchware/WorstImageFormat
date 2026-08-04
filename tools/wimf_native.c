#include "wimf_c.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WIMF_NATIVE_MAX_BYTES ((size_t)1024 * 1024 * 1024)

static int token(FILE* file, char* output, size_t capacity) {
    int value;
    do {
        value = fgetc(file);
        if (value == '#') while (value != '\n' && value != EOF) value = fgetc(file);
    } while (value != EOF && isspace((unsigned char)value));
    if (value == EOF) return 0;
    size_t length = 0;
    while (value != EOF && !isspace((unsigned char)value)) {
        if (length + 1 >= capacity) return 0;
        output[length++] = (char)value;
        value = fgetc(file);
    }
    output[length] = '\0';
    return length != 0;
}

static int parse_number(const char* text, unsigned long maximum, unsigned long* output) {
    char* end = NULL;
    errno = 0;
    unsigned long value = strtoul(text, &end, 10);
    if (errno == ERANGE || end == text || *end != '\0' || value > maximum) return 0;
    *output = value;
    return 1;
}

static int read_file(const char* path, uint8_t** data, size_t* size) {
    FILE* file = fopen(path, "rb");
    if (!file) return 0;
    if (fseek(file, 0, SEEK_END) || ftell(file) < 0) { fclose(file); return 0; }
    long length = ftell(file);
    if ((unsigned long)length > WIMF_NATIVE_MAX_BYTES) { fclose(file); return 0; }
    if (fseek(file, 0, SEEK_SET)) { fclose(file); return 0; }
    *data = length ? (uint8_t*)malloc((size_t)length) : NULL;
    *size = (size_t)length;
    int ok = !length || (*data && fread(*data, 1, *size, file) == *size);
    fclose(file);
    if (!ok) { free(*data); *data = NULL; *size = 0; }
    return ok;
}

static int write_file(const char* path, const uint8_t* data, size_t size) {
    FILE* file = fopen(path, "wb");
    if (!file) return 0;
    int ok = fwrite(data, 1, size, file) == size;
    if (fclose(file) != 0) ok = 0;
    return ok;
}

static int encode_pnm(const char* input, const char* output, int quality, int lossless) {
    FILE* file = fopen(input, "rb");
    char value[64];
    if (!file || !token(file, value, sizeof(value))) { if (file) fclose(file); return 1; }
    int channels = strcmp(value, "P5") == 0 ? 1 : strcmp(value, "P6") == 0 ? 3 : 0;
    if (!channels || !token(file, value, sizeof(value))) { fclose(file); return 1; }
    unsigned long width = 0;
    if (!parse_number(value, 65535, &width)) { fclose(file); return 1; }
    if (!token(file, value, sizeof(value))) { fclose(file); return 1; }
    unsigned long height = 0;
    if (!parse_number(value, 65535, &height) || !token(file, value, sizeof(value))) {
        fclose(file); return 1;
    }
    unsigned long maximum = 0;
    if (!parse_number(value, 255, &maximum) || maximum != 255 || !width || !height) {
        fclose(file); return 1;
    }
    if (width > SIZE_MAX / height / (unsigned)channels) { fclose(file); return 1; }
    size_t size = (size_t)width * height * (unsigned)channels;
    if (size > WIMF_NATIVE_MAX_BYTES) { fclose(file); return 1; }
    uint8_t* pixels = (uint8_t*)malloc(size);
    if (!pixels || fread(pixels, 1, size, file) != size) { free(pixels); fclose(file); return 1; }
    fclose(file);
    wimf_image_view image = {pixels, (uint32_t)width, (uint32_t)height, (uint8_t)channels, 1,
                             (size_t)width * (unsigned)channels};
    wimf_encode_options options; wimf_encode_options_init(&options);
    options.quality = (uint8_t)quality; options.lossless = (uint8_t)lossless;
    wimf_buffer encoded = {0};
    wimf_status status = wimf_encode(&image, &options, &encoded);
    free(pixels);
    if (status.code != WIMF_STATUS_OK) { fprintf(stderr, "wimf-native: %s\n", status.message); return 1; }
    int ok = write_file(output, encoded.data, encoded.size);
    wimf_buffer_free(&encoded);
    return ok ? 0 : 1;
}

static int decode_pnm(const char* input, const char* output) {
    uint8_t* encoded = NULL; size_t encoded_size = 0;
    if (!read_file(input, &encoded, &encoded_size)) return 1;
    wimf_decode_options options; wimf_decode_options_init(&options);
    wimf_decoded_image image = {0};
    wimf_status status = wimf_decode(encoded, encoded_size, &options, &image);
    free(encoded);
    if (status.code != WIMF_STATUS_OK) { fprintf(stderr, "wimf-native: %s\n", status.message); return 1; }
    if (image.bit_depth != 8 || (image.channels != 1 && image.channels != 3)) {
        fprintf(stderr, "wimf-native: PNM output supports only 8-bit grayscale or RGB\n");
        wimf_decoded_image_free(&image); return 1;
    }
    FILE* file = fopen(output, "wb");
    int ok = file != NULL;
    if (ok) ok = fprintf(file, "P%d\n%u %u\n255\n", image.channels == 1 ? 5 : 6, image.width, image.height) > 0;
    if (ok) ok = fwrite(image.pixels.data, 1, image.pixels.size, file) == image.pixels.size;
    if (file && fclose(file) != 0) ok = 0;
    wimf_decoded_image_free(&image);
    return ok ? 0 : 1;
}

int main(int argc, char** argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        printf("wimf-native %s (C ABI %u)\n", wimf_codec_version(), wimf_abi_version()); return 0;
    }
    if ((argc == 4 || argc == 6) && strcmp(argv[1], "encode") == 0) {
        int lossless = 1, quality = 7;
        if (argc == 6) {
            unsigned long parsed_quality = 0;
            if (strcmp(argv[4], "--lossy") != 0 || !parse_number(argv[5], 10, &parsed_quality) ||
                parsed_quality < 1) return 2;
            lossless = 0; quality = (int)parsed_quality;
        }
        if (quality < 1 || quality > 10) return 2;
        return encode_pnm(argv[2], argv[3], quality, lossless);
    }
    if (argc == 4 && strcmp(argv[1], "decode") == 0) return decode_pnm(argv[2], argv[3]);
    fprintf(stderr, "usage: wimf-native encode INPUT.pnm OUTPUT.wimf [--lossy 1..10]\n"
                    "       wimf-native decode INPUT.wimf OUTPUT.pnm\n");
    return 2;
}
