# Command-line tools

## Encode and decode

```bash
wimf encode source.png output.wimf --quality 7 --preset Balanced --codec auto
wimf encode source.png exact.wimf --lossless
wimf decode output.wimf decoded.png
```

## ROI and inspection

```bash
wimf decode large.wimf region.png --roi 256 128 512 512
wimf info output.wimf --json
wimf runtime --json
```

## Text transports

```bash
wimf base16 encode output.wimf output.hex
wimf base16 decode output.hex restored.wimf
wimf base32 encode output.wimf output.b32
wimf base32 decode output.b32 restored.wimf
wimf base64 encode output.wimf output.txt
wimf base64 encode output.wimf data-url.txt --data-url
wimf base64 decode output.txt restored.wimf
```

All three use strict RFC 4648 alphabets, tolerate whitespace, and enforce safety bounds. Base16, Base32, and Base64 expand the payload; they are transport encodings, not compression. Data URLs are Base64-only.

## Native process bridge

CMake installations include `wimf-native`, which converts 8-bit binary PGM/PPM files without Python:

```bash
wimf-native encode source.ppm output.wimf
wimf-native encode source.pgm output.wimf --lossy 7
wimf-native decode output.wimf restored.ppm
```

This deliberately small bridge is useful from shells and languages that can launch a process. Use the C ABI for direct memory integration and the Python CLI for PNG, JPEG, and other Pillow-supported files.

## Corruption diagnostics

```bash
wimf corrupt output.wimf damaged.wimf --seed 10 --count 4 --area payload
wimf diagnose damaged.wimf --json
wimf diagnose damaged.wimf --unsafe-preview preview.png
```

Unsafe previews are diagnostic images and cannot be saved as verified WIMF output.

`wimf-convert` and `wimf-meta` are deprecated in 2.2. Use the unified `wimf` command or WIMF Studio.
