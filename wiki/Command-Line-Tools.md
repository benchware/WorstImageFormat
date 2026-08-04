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

## Base64 transport

```bash
wimf base64 encode output.wimf output.txt
wimf base64 encode output.wimf data-url.txt --data-url
wimf base64 decode output.txt restored.wimf
```

## Corruption diagnostics

```bash
wimf corrupt output.wimf damaged.wimf --seed 10 --count 4 --area payload
wimf diagnose damaged.wimf --json
wimf diagnose damaged.wimf --unsafe-preview preview.png
```

Unsafe previews are diagnostic images and cannot be saved as verified WIMF output.

`wimf-convert` and `wimf-meta` are deprecated in 2.2. Use the unified `wimf` command or WIMF Studio.
