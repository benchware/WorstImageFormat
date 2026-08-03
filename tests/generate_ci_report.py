"""Generate human-readable codec evidence for GitHub Actions."""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wimf  # noqa: E402
from wimf.hybrid import MODE_NAMES, parse_v2  # noqa: E402


def encode_decode(image, *, lossless, quality=7, codec="auto"):
    start = time.perf_counter()
    payload = wimf.WIMFEncoder(image).encode(lossless=lossless, quality=quality, codec=codec, threads=4)
    encode_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    decoded = wimf.WIMFDecoder(payload).decode().pil
    decode_ms = (time.perf_counter() - start) * 1000
    return payload, decoded, encode_ms, decode_ms


def tile_modes(payload):
    counts = {name: 0 for name in MODE_NAMES.values()}
    for entry in parse_v2(payload)["entries"]:
        counts[MODE_NAMES[entry[4]]] += 1
    return {name: count for name, count in counts.items() if count}


def metrics(source, decoded, payload, encode_ms, decode_ms):
    a = np.asarray(source, dtype=np.float64)
    b = np.asarray(decoded, dtype=np.float64)
    error = a - b
    mse = float(np.mean(error**2))
    psnr = None if mse == 0 else 10 * math.log10(255**2 / mse)
    return {
        "bytes": len(payload),
        "ratio": source.width * source.height * len(source.getbands()) / len(payload),
        "mse": mse,
        "max_error": int(np.abs(error).max()),
        "psnr_db": psnr,
        "encode_ms": encode_ms,
        "decode_ms": decode_ms,
        "tile_modes": tile_modes(payload),
    }


def build_fixture(logo):
    width, height = 512, 256
    y, x = np.mgrid[:height, :width]
    canvas = np.empty((height, width, 4), dtype=np.uint8)
    canvas[..., 0] = x * 255 // (width - 1)
    canvas[..., 1] = y * 255 // (height - 1)
    canvas[..., 2] = (x + y) % 256
    canvas[..., 3] = 255
    palette = np.array([[20, 20, 20], [245, 245, 245], [30, 110, 230], [230, 60, 120]], dtype=np.uint8)
    palette_rng = np.random.default_rng(20260802)
    canvas[:128, :128, :3] = palette[palette_rng.integers(0, len(palette), (128, 128))]
    rng = np.random.default_rng(20260803)
    canvas[-48:, :, :3] = rng.integers(0, 256, (48, width, 3), dtype=np.uint8)
    fixture = Image.fromarray(canvas, "RGBA")
    logo.thumbnail((280, 150), Image.Resampling.LANCZOS)
    fixture.alpha_composite(logo, (width - logo.width - 20, 70))
    return fixture


def build_comparison(panels):
    source = panels[0][1]
    columns = 4
    rows = math.ceil(len(panels) / columns)
    label_height = 30
    comparison = Image.new("RGB", (source.width * columns, (source.height + label_height) * rows), "#0d1117")
    draw = ImageDraw.Draw(comparison)
    for index, (label, panel) in enumerate(panels):
        x = index % columns * source.width
        y = index // columns * (source.height + label_height)
        comparison.paste(panel.convert("RGB"), (x, y + label_height))
        draw.text((x + 10, y + 8), label, fill="white")
    return comparison


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    source = build_fixture(Image.open(args.input).convert("RGBA"))
    configurations = [
        ("lossless_auto", "Lossless auto", {"lossless": True, "codec": "auto"}),
        ("lossy_auto_q5", "Auto Q5", {"lossless": False, "quality": 5, "codec": "auto"}),
        ("predictive", "Predictive", {"lossless": True, "codec": "predictive"}),
        ("palette", "Palette", {"lossless": True, "codec": "palette"}),
        ("wavelet_q5", "Wavelet Q5", {"lossless": False, "quality": 5, "codec": "wavelet"}),
        ("raw", "Raw", {"lossless": True, "codec": "raw"}),
    ]
    results = {}
    decoded_images = {}
    payloads = {}
    for key, label, options in configurations:
        payload, decoded, encode_ms, decode_ms = encode_decode(source, **options)
        results[key] = {"label": label, **metrics(source, decoded, payload, encode_ms, decode_ms)}
        decoded_images[key] = decoded
        payloads[key] = payload

    if results["lossless_auto"]["max_error"] != 0:
        raise AssertionError("visual fixture failed its lossless roundtrip")
    if not {"palette", "predictive"} <= set(results["lossless_auto"]["tile_modes"]):
        raise AssertionError("visual fixture did not exercise mixed Palette/Predictive auto selection")

    source.save(args.output / "source.png")
    for key, image in decoded_images.items():
        filename = key.replace("_", "-")
        image.save(args.output / f"decoded-{filename}.png")
        (args.output / f"fixture-{filename}.wimf").write_bytes(payloads[key])
    difference = ImageEnhance.Contrast(ImageChops.difference(source, decoded_images["wavelet_q5"])).enhance(8)
    difference.save(args.output / "difference-8x.png")
    build_comparison(
        [
            ("Source", source),
            ("Lossless Auto", decoded_images["lossless_auto"]),
            ("Auto Q5", decoded_images["lossy_auto_q5"]),
            ("Predictive", decoded_images["predictive"]),
            ("Palette", decoded_images["palette"]),
            ("Wavelet Q5", decoded_images["wavelet_q5"]),
            ("Raw", decoded_images["raw"]),
            ("Wavelet difference (8x)", difference),
        ]
    ).save(args.output / "comparison.png")

    report = {"runtime": wimf.runtime_info(), "modes": results}
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    table_rows = []
    for result in results.values():
        psnr = "∞" if result["psnr_db"] is None else f"{result['psnr_db']:.2f} dB"
        modes = ", ".join(f"{name}: {count}" for name, count in result["tile_modes"].items())
        table_rows.append(
            f"| {result['label']} | {result['bytes']:,} B | {result['ratio']:.2f}× | "
            f"{result['mse']:.2f} | {result['max_error']} | {psnr} | {modes} | "
            f"{result['encode_ms']:.1f} ms | {result['decode_ms']:.1f} ms |"
        )
    summary = f"""## WIMF visual codec report

![Source and WIMF codec family comparison](https://raw.githubusercontent.com/{os.environ.get("GITHUB_REPOSITORY", "benchware/WorstImageFormat")}/{os.environ.get("GITHUB_SHA", "main")}/.github/assets/codec-preview.png)

| Configuration | Size | Ratio | MSE | Max error | PSNR | Selected tiles | Encode | Decode |
|---|---:|---:|---:|---:|---:|---|---:|---:|
{chr(10).join(table_rows)}

`auto` evaluates tile content and can mix Raw, Predictive, Palette, and Wavelet in one image.

Backend: `{report["runtime"]}`
"""
    (args.output / "summary.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
