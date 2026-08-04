#include <MagickCore/MagickCore.h>

#include "wimf_c.h"

static MagickBooleanType IsWIMF(const unsigned char *magick, const size_t length) {
  if (length < 4) return MagickFalse;
  return memcmp(magick, "WIM2", 4) == 0 || memcmp(magick, "WIMF", 4) == 0 ||
         memcmp(magick, "ROT!", 4) == 0;
}

static Image *ReadWIMFImage(const ImageInfo *image_info, ExceptionInfo *exception) {
  size_t length = 0;
  unsigned char *blob = FileToBlob(image_info->filename, ~(size_t)0, &length, exception);
  if (blob == NULL) return NULL;
  wimf_decode_options options; wimf_decode_options_init(&options);
  wimf_decoded_image decoded = {0};
  const wimf_status status = wimf_decode(blob, length, &options, &decoded);
  blob = (unsigned char *) RelinquishMagickMemory(blob);
  if (status.code != WIMF_STATUS_OK) {
    ThrowReaderException(CorruptImageError, status.message);
  }
  if (decoded.bit_depth != 8 || decoded.channels < 1 || decoded.channels > 4) {
    wimf_decoded_image_free(&decoded);
    ThrowReaderException(CoderError, "UnsupportedWIMFPixelLayout");
  }
  Image *image = AcquireImage(image_info, exception);
  image->columns = decoded.width; image->rows = decoded.height;
  image->depth = 8;
  if (decoded.channels == 2 || decoded.channels == 4) image->alpha_trait = BlendPixelTrait;
  if (SetImageExtent(image, image->columns, image->rows, exception) == MagickFalse) {
    wimf_decoded_image_free(&decoded); image = DestroyImage(image); return NULL;
  }
  for (size_t y = 0; y < image->rows; ++y) {
    Quantum *q = QueueAuthenticPixels(image, 0, (ssize_t)y, image->columns, 1, exception);
    if (q == NULL) { wimf_decoded_image_free(&decoded); image = DestroyImage(image); return NULL; }
    for (size_t x = 0; x < image->columns; ++x) {
      const unsigned char *p = decoded.pixels.data + (y * image->columns + x) * decoded.channels;
      const unsigned char r = p[0];
      const unsigned char g = decoded.channels >= 3 ? p[1] : r;
      const unsigned char b = decoded.channels >= 3 ? p[2] : r;
      const unsigned char a = (decoded.channels == 2 || decoded.channels == 4) ? p[decoded.channels - 1] : 255;
      SetPixelRed(image, ScaleCharToQuantum(r), q);
      SetPixelGreen(image, ScaleCharToQuantum(g), q);
      SetPixelBlue(image, ScaleCharToQuantum(b), q);
      SetPixelAlpha(image, ScaleCharToQuantum(a), q);
      q += GetPixelChannels(image);
    }
    if (SyncAuthenticPixels(image, exception) == MagickFalse) {
      wimf_decoded_image_free(&decoded); image = DestroyImage(image); return NULL;
    }
  }
  wimf_decoded_image_free(&decoded);
  return image;
}

ModuleExport size_t RegisterWIMFImage(void) {
  MagickInfo *entry = AcquireMagickInfo("WIMF", "WIMF", "WIM2 hybrid image");
  entry->decoder = (DecodeImageHandler *) ReadWIMFImage;
  entry->magick = (IsImageFormatHandler *) IsWIMF;
  entry->flags ^= CoderAdjoinFlag;
  (void) RegisterMagickInfo(entry);
  return MagickImageCoderSignature;
}

ModuleExport void UnregisterWIMFImage(void) { (void) UnregisterMagickInfo("WIMF"); }
