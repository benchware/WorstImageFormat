"""Cross-platform Python-versus-C++ benchmark for current WIM2 still images."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from wimf import core, hybrid


def timed(operation):
    start = time.perf_counter()
    result = operation()
    return result, time.perf_counter() - start


def still_source(size):
    y, x = np.indices((size, size))
    return np.stack(((x * 3 + y) & 255, (x + y * 5) & 255, (x * 7 + y * 2) & 255), axis=2).astype(np.uint8)


def benchmark_wim2(image, native_backend):
    saved_native = hybrid.native
    hybrid.native = native_backend
    try:
        payload, encode_s = timed(
            lambda: hybrid.encode_v2(
                image.tobytes(), image.shape[1], image.shape[0], 3, quality=5, preset="Balanced", threads=4
            )
        )
        _, decode_s = timed(lambda: hybrid.decode_v2(payload))
    finally:
        hybrid.native = saved_native
    megapixels = image.shape[0] * image.shape[1] / 1_000_000
    return {
        "bytes": len(payload),
        "encode_mpx_s": megapixels / encode_s,
        "decode_mpx_s": megapixels / decode_s,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--still-size", type=int, default=512)
    args = parser.parse_args()
    native_module = hybrid.native
    native_available = native_module is not None and core.HAS_CPP
    still = still_source(args.still_size)
    report = {
        "configuration": vars(args),
        "native_available": native_available,
        "wim2": {
            "python": benchmark_wim2(still, None),
            "cpp": benchmark_wim2(still, native_module) if native_module is not None else None,
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
