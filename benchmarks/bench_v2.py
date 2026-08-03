"""Small reproducible WIMF v2 throughput benchmark."""

import argparse
import sys
import time
from pathlib import Path

# Keep the benchmark runnable directly from a source checkout, as CI does.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

import wimf
from wimf.hybrid import decode_v2, encode_v2


def measure(size, threads):
    rng = np.random.default_rng(42)
    image = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
    start = time.perf_counter()
    encoded = encode_v2(image.tobytes(), size, size, 3, quality=7, preset="Balanced", threads=threads)
    encode_seconds = time.perf_counter() - start
    start = time.perf_counter()
    decode_v2(encoded)
    decode_seconds = time.perf_counter() - start
    megapixels = size * size / 1_000_000
    print(
        f"{size}x{size}: {len(encoded):,} bytes | encode {megapixels / encode_seconds:.2f} MP/s | "
        f"decode {megapixels / decode_seconds:.2f} MP/s"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, choices=(512, 3840), default=512)
    parser.add_argument("--threads", type=int)
    args = parser.parse_args()
    print(wimf.runtime_info())
    measure(args.size, args.threads)


if __name__ == "__main__":
    main()
