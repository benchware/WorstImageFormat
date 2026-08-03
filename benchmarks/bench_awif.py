"""Compare legacy AWIF's Python and C++-accelerated execution paths."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from wimf import animation, codec, core


def frames(width, height, count):
    y, x = np.indices((height, width))
    return [
        np.stack(((x + i * 5) & 255, (y * 2 + i * 3) & 255, (x + y + i * 7) & 255), axis=2).astype(np.uint8).tobytes()
        for i in range(count)
    ]


def measure(label, source, width, height, quality, preset, native, available):
    core.HAS_CPP = codec.HAS_CPP = animation.HAS_CPP = native and available
    start = time.perf_counter()
    payload = animation.encode_animated(source, width, height, 3, quality, preset)
    encode_s = time.perf_counter() - start
    start = time.perf_counter()
    decoded = animation.decode_animated(payload, width, height, 3)
    decode_s = time.perf_counter() - start
    pixels = width * height * len(source) / 1_000_000
    return {
        "backend": label,
        "native_available": available,
        "bytes": len(payload),
        "encode_mpx_s": pixels / encode_s,
        "decode_mpx_s": pixels / decode_s,
        "frames": len(decoded),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--quality", type=int, default=5)
    parser.add_argument("--preset", choices=["Fast", "Balanced", "Extreme"], default="Balanced")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    source = frames(args.width, args.height, args.frames)
    native_available = core.HAS_CPP
    results = [
        measure("python", source, args.width, args.height, args.quality, args.preset, False, native_available),
        measure(
            "cpp-accelerated",
            source,
            args.width,
            args.height,
            args.quality,
            args.preset,
            True,
            native_available,
        ),
    ]
    if args.json:
        print(json.dumps({"configuration": vars(args), "results": results}, indent=2))
    else:
        for result in results:
            print(
                f"{result['backend']}: {result['bytes']:,} bytes | encode {result['encode_mpx_s']:.2f} MP/s | "
                f"decode {result['decode_mpx_s']:.2f} MP/s"
            )


if __name__ == "__main__":
    main()
