# FFmpeg WIMF decoder integration

FFmpeg codecs are registered at build time; there is no supported third-party
runtime codec plugin interface. `wimfdec.c` is therefore an upstream-oriented
libavcodec source integration using WIMF's stable C ABI.

Against an FFmpeg source checkout:

1. Copy `wimfdec.c` into `libavcodec/` and make `wimf_c.h` available.
2. Add `AV_CODEC_ID_WIMF` to `libavcodec/codec_id.h` in the still-image range.
3. Add `extern const FFCodec ff_wimf_decoder;` to `libavcodec/allcodecs.c`.
4. Add `OBJS-$(CONFIG_WIMF_DECODER) += wimfdec.o` to `libavcodec/Makefile`.
5. Add the WIMF library/header probe and `wimf_decoder_deps="wimf"` to
   `configure`, then build with `--enable-gpl --enable-libwimf`.

The GPL flags are required because WIMF is GPL-3.0-or-later. Upstream submission
also requires an FFmpeg-assigned codec ID, fate samples, fate tests, and review;
this repository cannot reserve the public ID unilaterally.
