"""Generate human-readable, multi-fixture codec evidence for GitHub Actions."""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wimf  # noqa: E402
from wimf.hybrid import MODE_NAMES, parse_v2  # noqa: E402

THREADS = 4
CONFIGURATIONS = [
    ("lossless_auto", "Lossless Auto", {"lossless": True, "quality": 7, "preset": "Balanced", "codec": "auto"}),
    ("lossy_auto_q5", "Lossy Auto Q5", {"lossless": False, "quality": 5, "preset": "Balanced", "codec": "auto"}),
    ("predictive", "Predictive", {"lossless": True, "quality": 7, "preset": "Balanced", "codec": "predictive"}),
    ("palette", "Palette", {"lossless": True, "quality": 7, "preset": "Balanced", "codec": "palette"}),
    ("wavelet_q5", "Wavelet Q5", {"lossless": False, "quality": 5, "preset": "Balanced", "codec": "wavelet"}),
    ("raw", "Raw", {"lossless": True, "quality": 7, "preset": "Balanced", "codec": "raw"}),
]


def encode_decode(image, options):
    start = time.perf_counter()
    payload = wimf.WIMFEncoder(image).encode(**options, threads=THREADS)
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
    raw_bytes = source.width * source.height * len(source.getbands())
    return {
        "bytes": len(payload),
        "ratio": raw_bytes / len(payload),
        "mse": mse,
        "max_error": int(np.abs(error).max()),
        "psnr_db": psnr,
        "encode_ms": encode_ms,
        "decode_ms": decode_ms,
        "encode_mpx_s": source.width * source.height / max(encode_ms, 0.001) / 1000,
        "decode_mpx_s": source.width * source.height / max(decode_ms, 0.001) / 1000,
        "tile_modes": tile_modes(payload),
    }


def build_synthetic_fixture(logo):
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


def photo_fixture(path):
    with Image.open(path) as image:
        return ImageOps.fit(image.convert("RGB"), (512, 320), Image.Resampling.LANCZOS)


def build_comparison(panels):
    panel_width, panel_height = panels[0][1].size
    columns = 2
    rows = math.ceil(len(panels) / columns)
    label_height = 36
    comparison = Image.new("RGB", (panel_width * columns, (panel_height + label_height) * rows), "#0d1117")
    draw = ImageDraw.Draw(comparison)
    for index, (label, panel) in enumerate(panels):
        x = index % columns * panel_width
        y = index // columns * (panel_height + label_height)
        comparison.paste(panel.convert("RGB"), (x, y + label_height))
        draw.text((x + 10, y + 10), label, fill="white")
    return comparison


def options_text(options):
    return ", ".join(
        [
            f"codec={options['codec']}",
            f"lossless={str(options['lossless']).lower()}",
            f"quality={options['quality']}",
            f"preset={options['preset']}",
            f"threads={THREADS}",
            "tile=128x128",
            "format=WIM2",
        ]
    )


def report_fixture(slug, title, source, credit, output, preview_dir):
    fixture_dir = output / slug
    fixture_dir.mkdir(parents=True, exist_ok=True)
    source.save(fixture_dir / "source.png")
    results, decoded_images = {}, {}
    for key, label, options in CONFIGURATIONS:
        payload, decoded, encode_ms, decode_ms = encode_decode(source, options)
        results[key] = {
            "label": label,
            "configuration": options_text(options),
            "options": {**options, "threads": THREADS, "tile_size": 128, "format_version": 2},
            **metrics(source, decoded, payload, encode_ms, decode_ms),
        }
        decoded_images[key] = decoded
        decoded.save(fixture_dir / f"decoded-{key.replace('_', '-')}.png")
        (fixture_dir / f"{slug}-{key.replace('_', '-')}.wimf").write_bytes(payload)

    if results["lossless_auto"]["max_error"] != 0:
        raise AssertionError(f"{slug} failed its lossless roundtrip")
    if slug == "synthetic-mixed" and not {"palette", "predictive"} <= set(results["lossless_auto"]["tile_modes"]):
        raise AssertionError("synthetic fixture did not exercise mixed Palette/Predictive auto selection")

    difference = ImageEnhance.Contrast(ImageChops.difference(source, decoded_images["wavelet_q5"])).enhance(8)
    difference.save(fixture_dir / "wavelet-difference-8x.png")
    comparison = build_comparison(
        [("Source", source)]
        + [(label, decoded_images[key]) for key, label, _ in CONFIGURATIONS]
        + [("Wavelet difference (8x)", difference)]
    )
    comparison.save(fixture_dir / "comparison.png")
    preview_dir.mkdir(parents=True, exist_ok=True)
    comparison.save(preview_dir / f"{slug}.png", optimize=True)
    (fixture_dir / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return {"title": title, "credit": credit, "dimensions": list(source.size), "modes": results}


def fixture_summary(slug, fixture, repository, sha):
    rows = []
    for result in fixture["modes"].values():
        psnr = "∞" if result["psnr_db"] is None else f"{result['psnr_db']:.2f} dB"
        modes = ", ".join(f"{name}: {count}" for name, count in result["tile_modes"].items())
        rows.append(
            f"| {result['label']} | `{result['configuration']}` | {result['bytes']:,} B | {result['ratio']:.2f}× | "
            f"{result['mse']:.2f} | {result['max_error']} | {psnr} | {modes} | "
            f"{result['encode_ms']:.1f} ms ({result['encode_mpx_s']:.1f} MP/s) | "
            f"{result['decode_ms']:.1f} ms ({result['decode_mpx_s']:.1f} MP/s) |"
        )
    credit = fixture["credit"]
    return f"""### {fixture["title"]} ({fixture["dimensions"][0]}×{fixture["dimensions"][1]})

{credit}

![{fixture["title"]} codec comparison](https://raw.githubusercontent.com/{repository}/{sha}/.github/assets/report-previews/{slug}.png)

| Configuration | Exact settings | Size | Ratio | MSE | Max error | PSNR | Selected tiles | Encode | Decode |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|
{chr(10).join(rows)}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="WIMF logo used by the synthetic fixture")
    parser.add_argument("--fixtures", type=Path, default=Path(".github/assets/fixtures"))
    parser.add_argument("--preview-dir", type=Path, default=Path(".github/assets/report-previews"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    fixtures = [
        (
            "synthetic-mixed",
            "Synthetic mixed-content stress test",
            build_synthetic_fixture(Image.open(args.input).convert("RGBA")),
            "Generated by the WIMF project; designed to exercise gradients, transparency, palettes, noise, and text.",
        ),
        (
            "glacier-lake",
            "Nature photograph — Lake McDonald, Glacier National Park",
            photo_fixture(args.fixtures / "glacier-lake.jpg"),
            "Credit: [NPS Natural Resources / National Park Service (public domain)](https://commons.wikimedia.org/wiki/File:National_Park_Service_(48754075203).jpg).",
        ),
        (
            "blue-fox",
            "Animal photograph — blue fox on St. Paul Island",
            photo_fixture(args.fixtures / "blue-fox.jpg"),
            "Credit: [Ryan Mong / U.S. Fish & Wildlife Service (public domain)](https://commons.wikimedia.org/wiki/File:Blue_fox_on_St_Paul_Island_by_Ryan_Mong_USFWS.jpg).",
        ),
    ]
    report = {
        "runtime": wimf.runtime_info(),
        "fixtures": {
            slug: report_fixture(slug, title, source, credit, args.output, args.preview_dir)
            for slug, title, source, credit in fixtures
        },
    }
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    repository = os.environ.get("GITHUB_REPOSITORY", "benchware/WorstImageFormat")
    sha = os.environ.get("GITHUB_SHA", "main")
    sections = [fixture_summary(slug, fixture, repository, sha) for slug, fixture in report["fixtures"].items()]
    summary = f"""## WIMF visual codec report

Each fixture is reported separately so photographic behavior cannot hide behind synthetic averages. Every row records the exact public encoder configuration used for that run. Full-resolution decoded images, differences, WIMF payloads, and JSON data are available in the artifact.

{"".join(sections)}
### Runtime

```json
{json.dumps(report["runtime"], indent=2)}
```

`auto` evaluates each tile independently and may mix Raw, Predictive, Palette, and Wavelet in one image. Timings are diagnostic CI measurements, not release benchmarks.
"""
    (args.output / "summary.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
