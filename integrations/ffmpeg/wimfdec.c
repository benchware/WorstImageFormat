/* Copy into FFmpeg's libavcodec/ tree; see README.md for registration changes. */
#include <string.h>

#include "avcodec.h"
#include "codec_internal.h"
#include "decode.h"
#include "libavutil/error.h"
#include "libavutil/pixfmt.h"
#include "wimf_c.h"

static int wimf_decode_frame(AVCodecContext *avctx, AVFrame *frame,
                             int *got_frame, AVPacket *packet) {
    wimf_decode_options options; wimf_decode_options_init(&options);
    wimf_decoded_image image = {0};
    const wimf_status status = wimf_decode(packet->data, packet->size, &options, &image);
    if (status.code != WIMF_STATUS_OK) {
        av_log(avctx, AV_LOG_ERROR, "WIMF decode failed: %s\n", status.message);
        return AVERROR_INVALIDDATA;
    }
    if (image.channels < 1 || image.channels > 4) {
        wimf_decoded_image_free(&image); return AVERROR_PATCHWELCOME;
    }
    const int high = image.bit_depth > 8;
    if (image.channels == 1) avctx->pix_fmt = high ? AV_PIX_FMT_GRAY16LE : AV_PIX_FMT_GRAY8;
    else if (image.channels == 3) avctx->pix_fmt = high ? AV_PIX_FMT_RGB48LE : AV_PIX_FMT_RGB24;
    else avctx->pix_fmt = high ? AV_PIX_FMT_RGBA64LE : AV_PIX_FMT_RGBA;
    if (ff_set_dimensions(avctx, image.width, image.height) < 0) {
        wimf_decoded_image_free(&image); return AVERROR_INVALIDDATA;
    }
    frame->format = avctx->pix_fmt;
    frame->width = image.width; frame->height = image.height;
    int result = ff_get_buffer(avctx, frame, 0);
    if (result < 0) { wimf_decoded_image_free(&image); return result; }
    const int bytes = high ? 2 : 1;
    const int output_channels = (image.channels == 1 || image.channels == 3) ? image.channels : 4;
    for (uint32_t y = 0; y < image.height; ++y) {
        uint8_t *target = frame->data[0] + y * frame->linesize[0];
        const uint8_t *source = image.pixels.data + (size_t)y * image.width * image.channels * bytes;
        if (image.channels == output_channels) {
            memcpy(target, source, (size_t)image.width * output_channels * bytes);
        } else {
            for (uint32_t x = 0; x < image.width; ++x) {
                const uint8_t *pixel = source + (size_t)x * image.channels * bytes;
                uint8_t *out = target + (size_t)x * 4 * bytes;
                memcpy(out, pixel, bytes); memcpy(out + bytes, pixel, bytes); memcpy(out + 2 * bytes, pixel, bytes);
                memcpy(out + 3 * bytes, pixel + bytes, bytes);
            }
        }
    }
    wimf_decoded_image_free(&image);
    *got_frame = 1;
    return packet->size;
}

const FFCodec ff_wimf_decoder = {
    .p.name = "wimf",
    CODEC_LONG_NAME("WIM2 hybrid image"),
    .p.type = AVMEDIA_TYPE_VIDEO,
    .p.id = AV_CODEC_ID_WIMF,
    .p.capabilities = AV_CODEC_CAP_DR1,
    FF_CODEC_DECODE_CB(wimf_decode_frame),
};
