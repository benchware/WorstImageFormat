"""Render codec benchmark JSON as a Markdown fragment for CI job summaries."""

import json
import os
import sys


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "codec-benchmark.json"
    with open(source, encoding="utf-8") as handle:
        data = json.load(handle)
    results = data["wim2"]
    runner = os.environ.get("RUNNER_OS", "unknown")
    sample = data.get("configuration", {}).get("still_size", "?")
    native = results["cpp"]
    reference = results["python"]

    print(f"## Codec throughput - {runner} ({sample}px synthetic sample)")
    print()
    print("| Backend | Encode MP/s | Decode MP/s | Size (bytes) |")
    print("|---|---:|---:|---:|")
    native_row = f"| C++ native | {native['encode_mpx_s']:.1f} | {native['decode_mpx_s']:.1f} | {native['bytes']} |"
    reference_row = (
        f"| Python reference | {reference['encode_mpx_s']:.1f} "
        f"| {reference['decode_mpx_s']:.1f} | {reference['bytes']} |"
    )
    print(native_row)
    print(reference_row)
    if native["encode_mpx_s"] > 0 and native["decode_mpx_s"] > 0:
        encode_speedup = reference["encode_mpx_s"] / native["encode_mpx_s"]
        decode_speedup = reference["decode_mpx_s"] / native["decode_mpx_s"]
        print(f"| Native speedup | {encode_speedup:.0f}x | {decode_speedup:.0f}x | - |")
    print()
    print("Each runner is different hardware: compare within a table, not across tables or runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
