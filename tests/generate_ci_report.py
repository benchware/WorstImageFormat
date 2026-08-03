"""Generate human-readable codec evidence for GitHub Actions."""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageEnhance

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wimf  # noqa: E402


def encode_decode(image, *, lossless, quality=7, codec="auto"):
    start = time.perf_counter()
    payload = wimf.WIMFEncoder(image).encode(lossless=lossless, quality=quality, codec=codec, threads=4)
    encode_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    decoded = wimf.WIMFDecoder(payload).decode().pil
    decode_ms = (time.perf_counter() - start) * 1000
    return payload, decoded, encode_ms, decode_ms


def metrics(source, decoded, encoded_size, encode_ms, decode_ms):
    a = np.asarray(source, dtype=np.float64)
    b = np.asarray(decoded, dtype=np.float64)
    error = a - b
    mse = float(np.mean(error**2))
    psnr = None if mse == 0 else 10 * math.log10(255**2 / mse)
    return {
        "bytes": encoded_size,
        "ratio": source.width * source.height * len(source.getbands()) / encoded_size,
        "mse": mse,
        "max_error": int(np.abs(error).max()),
        "psnr_db": psnr,
        "encode_ms": encode_ms,
        "decode_ms": decode_ms,
    }


def build_fixture(logo):
    width, height = 384, 256
    y, x = np.mgrid[:height, :width]
    canvas = np.empty((height, width, 4), dtype=np.uint8)
    canvas[..., 0] = x * 255 // (width - 1)
    canvas[..., 1] = y * 255 // (height - 1)
    canvas[..., 2] = (x + y) % 256
    canvas[..., 3] = 255
    canvas[:96, :128, :3] = np.where(((x[:96, :128] // 8 + y[:96, :128] // 8) % 2)[..., None], 245, 20)
    rng = np.random.default_rng(20260803)
    canvas[-48:, :, :3] = rng.integers(0, 256, (48, width, 3), dtype=np.uint8)
    fixture = Image.fromarray(canvas, "RGBA")
    logo.thumbnail((280, 150), Image.Resampling.LANCZOS)
    fixture.alpha_composite(logo, ((width - logo.width) // 2, 70))
    return fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    source = build_fixture(Image.open(args.input).convert("RGBA"))
    lossless_payload, lossless_image, lossless_encode, lossless_decode = encode_decode(source, lossless=True)
    lossy_payload, lossy_image, lossy_encode, lossy_decode = encode_decode(
        source, lossless=False, quality=5, codec="wavelet"
    )
    lossless = metrics(source, lossless_image, len(lossless_payload), lossless_encode, lossless_decode)
    lossy = metrics(source, lossy_image, len(lossy_payload), lossy_encode, lossy_decode)
    if lossless["max_error"] != 0:
        raise AssertionError("visual fixture failed its lossless roundtrip")

    source.save(args.output / "source.png")
    lossless_image.save(args.output / "decoded-lossless.png")
    lossy_image.save(args.output / "decoded-lossy.png")
    difference = ImageChops.difference(source, lossy_image)
    ImageEnhance.Contrast(difference).enhance(8).save(args.output / "difference-8x.png")
    (args.output / "fixture-lossless.wimf").write_bytes(lossless_payload)
    (args.output / "fixture-lossy.wimf").write_bytes(lossy_payload)

    report = {"runtime": wimf.runtime_info(), "lossless": lossless, "lossy_wavelet_q5": lossy}
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    psnr = "∞" if lossy["psnr_db"] is None else f"{lossy['psnr_db']:.2f}"
    summary = f"""## WIMF visual codec report

![WIMF test fixture](https://raw.githubusercontent.com/{os.environ.get("GITHUB_REPOSITORY", "benchware/WorstImageFormat")}/{os.environ.get("GITHUB_SHA", "main")}/.github/assets/dark.png)

| Mode | Size | Ratio | MSE | Max error | PSNR | Encode | Decode |
|---|---:|---:|---:|---:|---:|---:|---:|
| Lossless | {lossless["bytes"]:,} B | {lossless["ratio"]:.2f}× | {lossless["mse"]:.2f} | {lossless["max_error"]} | ∞ | {lossless["encode_ms"]:.1f} ms | {lossless["decode_ms"]:.1f} ms |
| Wavelet Q5 | {lossy["bytes"]:,} B | {lossy["ratio"]:.2f}× | {lossy["mse"]:.2f} | {lossy["max_error"]} | {psnr} dB | {lossy["encode_ms"]:.1f} ms | {lossy["decode_ms"]:.1f} ms |

Backend: `{report["runtime"]}`
"""
    (args.output / "summary.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
