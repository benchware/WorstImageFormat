"""Render a Mandelbrot set and encode it directly as a WIMF image."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

# Make the example runnable from a source checkout before installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wimf


def render_mandelbrot(
    width: int,
    height: int,
    iterations: int,
    center_x: float,
    center_y: float,
    span: float,
) -> np.ndarray:
    """Return an RGB Mandelbrot rendering as a uint8 NumPy array."""
    if width < 1 or height < 1 or iterations < 1 or span <= 0:
        raise ValueError("width, height, iterations, and span must be positive")

    aspect = height / width
    real = np.linspace(center_x - span / 2, center_x + span / 2, width, dtype=np.float64)
    imaginary = np.linspace(center_y - span * aspect / 2, center_y + span * aspect / 2, height, dtype=np.float64)
    c = real[np.newaxis, :] + 1j * imaginary[:, np.newaxis]

    z = np.zeros(c.shape, dtype=np.complex128)
    active = np.ones(c.shape, dtype=bool)
    escape = np.full(c.shape, float(iterations), dtype=np.float64)

    for step in range(iterations):
        z[active] = z[active] * z[active] + c[active]
        escaped = active & (z.real * z.real + z.imag * z.imag > 4.0)
        if escaped.any():
            # Fractional escape time produces smoother bands without changing the set.
            magnitude = np.abs(z[escaped])
            escape[escaped] = step + 1 - np.log2(np.log2(magnitude))
            active[escaped] = False
        if not active.any():
            break

    normalized = np.clip(escape / iterations, 0.0, 1.0)
    phase = np.sqrt(normalized)

    # A compact polynomial palette: dark navy through cyan, gold, and white.
    red = 9.0 * (1.0 - phase) * phase**3
    green = 15.0 * (1.0 - phase) ** 2 * phase**2
    blue = 8.5 * (1.0 - phase) ** 3 * phase
    rgb = np.stack((red, green, blue), axis=-1)
    rgb = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    rgb[active] = 0
    return rgb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="mandelbrot.wimf", type=Path)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--center-x", type=float, default=-0.5)
    parser.add_argument("--center-y", type=float, default=0.0)
    parser.add_argument("--span", type=float, default=3.2, help="Width of the complex-plane view")
    parser.add_argument("--quality", type=int, choices=range(1, 11), default=7)
    parser.add_argument("--lossless", action="store_true")
    parser.add_argument("--codec", choices=("auto", "wavelet", "predictive", "palette", "raw"), default="auto")
    parser.add_argument("--preset", choices=("Fast", "Balanced", "Extreme"), default="Balanced")
    parser.add_argument("--threads", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output if args.output.suffix.lower() == ".wimf" else args.output.with_suffix(".wimf")

    started = time.perf_counter()
    image = render_mandelbrot(
        args.width,
        args.height,
        args.iterations,
        args.center_x,
        args.center_y,
        args.span,
    )
    render_seconds = time.perf_counter() - started

    encode_started = time.perf_counter()
    wimf.save(
        output,
        image,
        quality=args.quality,
        lossless=args.lossless,
        codec=args.codec,
        preset=args.preset,
        threads=args.threads,
        generator="examples/mandelbrot_wimf.py",
        fractal="Mandelbrot",
        iterations=args.iterations,
        center=[args.center_x, args.center_y],
        span=args.span,
    )
    encode_seconds = time.perf_counter() - encode_started

    print(f"Wrote {output} ({output.stat().st_size:,} bytes)")
    print(f"Rendered in {render_seconds:.3f}s; encoded in {encode_seconds:.3f}s")
    print(f"Runtime: {wimf.runtime_info()}")


if __name__ == "__main__":
    main()
