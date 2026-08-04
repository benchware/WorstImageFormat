# ImageMagick WIMF coder

This optional ImageMagick 7 decoder module recognizes WIM2 and legacy WIMF
magic and decodes through `wimf_c.h`. Build with:

```bash
cmake -S . -B build-magick -DWIMF_BUILD_IMAGEMAGICK=ON -DBUILD_SHARED_LIBS=ON
cmake --build build-magick
```

Install the resulting `wimf` module in ImageMagick's configured coder module
directory. Module directories and quantum/HDRI ABI names are distribution-
specific; verify them with `magick -version` and `magick -list module`.
The initial module is decode-only and supports 8-bit grayscale, grayscale-alpha,
RGB, and RGBA WIM2 output.
