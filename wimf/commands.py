"""Friendly, unified command-line interface for common WIMF workflows."""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import wimf

from .diagnostics import AREAS, corrupt, diagnose, unsafe_preview


def _output_path(source, requested, suffix):
    return Path(requested) if requested else Path(source).with_suffix(suffix)


def _metadata(values):
    result = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"metadata must use KEY=VALUE syntax: {value!r}")
        key, raw = value.split("=", 1)
        if not key:
            raise ValueError("metadata keys cannot be empty")
        try:
            result[key] = json.loads(raw)
        except json.JSONDecodeError:
            result[key] = raw
    return result


def _positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _encode(args):
    source = Path(args.input)
    output = _output_path(source, args.output, ".wimf")
    with Image.open(source) as image:
        image.load()
        wimf.save(
            output,
            image,
            quality=args.quality,
            lossless=args.lossless,
            preset=args.preset,
            codec=args.codec,
            threads=args.threads,
            anti_rot=args.anti_rot,
            metadata=_metadata(args.metadata),
        )
    original_size = source.stat().st_size
    encoded_size = output.stat().st_size
    ratio = encoded_size / original_size if original_size else 0
    print(f"Encoded {source} -> {output}")
    print(f"{encoded_size:,} bytes ({ratio:.2f}x the source size)")


def _decode(args):
    source = Path(args.input)
    output = _output_path(source, args.output, ".png")
    image = wimf.decode(source, roi=tuple(args.roi) if args.roi else None)
    image.pil.save(output)
    print(f"Decoded {source} -> {output}")


def _thumbnail(args):
    output = Path(args.output)
    if output.exists() and not args.force:
        raise ValueError(f"refusing to overwrite {str(output)!r}; pass --force")
    image = wimf.decode(args.input).pil
    image.thumbnail((args.size, args.size), Image.Resampling.LANCZOS)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    image.save(output, format="PNG")


def _info(args):
    result = wimf.inspect(args.input)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(
        f"{result['format']} | {result['width']}x{result['height']} | {result['channels']} channels | {result['bit_depth']}-bit"
    )
    print(f"Protected: {'yes' if result['protected'] else 'no'} | History states: {result['history_states']}")
    if "tile_modes" in result:
        modes = ", ".join(f"{name}={count}" for name, count in result["tile_modes"].items() if count)
        print(f"Tiles: {modes or 'none'}")
    if result["metadata"]:
        print("Metadata:")
        for key, value in sorted(result["metadata"].items()):
            print(f"  {key}: {value}")


def _runtime(args):
    details = wimf.runtime_info()
    if args.json:
        print(json.dumps(details, indent=2, sort_keys=True))
        return
    backend = "native C++" if details["native"] else "Python fallback"
    print(f"Backend: {backend}")
    print(f"Codec: {details['codec_version']} | Zstandard: {details['zstandard_version']}")
    print(f"CPU: {details['architecture']} | SIMD: {details['simd']} | Threads: {details['effective_threads']}")


def _view(args):
    from .studio import launch

    launch(args.input)


def _read_stream(path, *, binary=False):
    if path == "-":
        return sys.stdin.buffer.read() if binary else sys.stdin.read()
    mode = "rb" if binary else "r"
    kwargs = {} if binary else {"encoding": "ascii"}
    with open(path, mode, **kwargs) as stream:
        return stream.read()


def _write_stream(path, value, *, binary=False, force=False):
    if path == "-":
        target = sys.stdout.buffer if binary else sys.stdout
        target.write(value)
        if not binary and not value.endswith("\n"):
            target.write("\n")
        return
    if os.path.exists(path) and not force:
        raise ValueError(f"refusing to overwrite {path!r}; pass --force")
    mode = "wb" if binary else "w"
    kwargs = {} if binary else {"encoding": "ascii", "newline": ""}
    with open(path, mode, **kwargs) as stream:
        stream.write(value)


def _base64_encode(args):
    value = wimf.to_data_url(args.input) if args.data_url else wimf.to_base64(args.input, wrap=args.wrap)
    _write_stream(args.output, value, force=args.force)


def _base64_decode(args):
    value = _read_stream(args.input)
    decoded = wimf.from_data_url(value) if value.lstrip().startswith("data:") else wimf.from_base64(value)
    if not wimf.is_wimf(decoded):
        raise ValueError("decoded Base64 is not a supported WIMF container")
    _write_stream(args.output, decoded, binary=True, force=args.force)


def _base_encode(args):
    encoder = wimf.to_base16 if args.transport == "base16" else wimf.to_base32
    _write_stream(args.output, encoder(args.input, wrap=args.wrap), force=args.force)


def _base_decode(args):
    decoder = wimf.from_base16 if args.transport == "base16" else wimf.from_base32
    decoded = decoder(_read_stream(args.input))
    if not wimf.is_wimf(decoded):
        raise ValueError(f"decoded {args.transport} is not a supported WIMF container")
    _write_stream(args.output, decoded, binary=True, force=args.force)


def _add_base_transport(commands, name):
    parser = commands.add_parser(name, help=f"convert WIMF to or from RFC 4648 {name.title()} text")
    subcommands = parser.add_subparsers(dest=f"{name}_command", required=True)
    encode = subcommands.add_parser("encode", help=f"encode a WIMF file as {name.title()}")
    encode.add_argument("input")
    encode.add_argument("output", nargs="?", default="-")
    encode.add_argument("--wrap", type=int, default=0)
    encode.add_argument("--force", action="store_true")
    encode.set_defaults(handler=_base_encode, transport=name)
    decode = subcommands.add_parser("decode", help=f"decode {name.title()} into a WIMF file")
    decode.add_argument("input")
    decode.add_argument("output")
    decode.add_argument("--force", action="store_true")
    decode.set_defaults(handler=_base_decode, transport=name)


def _corrupt(args):
    source = Path(args.input).read_bytes()
    damaged = corrupt(
        source,
        seed=args.seed,
        count=args.count,
        area=args.area,
        tile=tuple(args.tile) if args.tile else None,
        mutation=args.mutation,
        truncate=args.truncate,
    )
    _write_stream(args.output, damaged, binary=True, force=args.force)
    print(f"Wrote {len(damaged):,} corrupted bytes to {args.output}")


def _diagnose(args):
    source = Path(args.input).read_bytes()
    report = diagnose(source)
    if args.unsafe_preview:
        array, failed = unsafe_preview(source)
        display = array
        if display.dtype != np.uint8:
            display = np.rint(display.astype(np.float64) * (255 / max(1, (1 << report["bit_depth"]) - 1))).astype(
                np.uint8
            )
        if display.shape[2] == 1:
            image = Image.fromarray(display[..., 0], "L")
        else:
            image = Image.fromarray(display[..., :4], "RGBA" if display.shape[2] >= 4 else "RGB")
        image = image.convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, min(image.width, 300), 22), fill=(180, 0, 0))
        draw.text((5, 5), "UNSAFE CORRUPTION PREVIEW", fill="white")
        image.save(args.unsafe_preview)
        report["unsafe_preview"] = str(args.unsafe_preview)
        report["failed_tiles"] = failed
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        state = "valid" if report["strict_ok"] else f"rejected: {report['strict_error']}"
        print(f"Strict decode: {state}")
        bad = [tile for tile in report.get("tiles", []) if not tile["checksum_valid"]]
        print(f"Tiles: {len(report.get('tiles', []))} total, {len(bad)} damaged")
        if args.unsafe_preview:
            print(f"UNSAFE diagnostic preview: {args.unsafe_preview}")


def build_parser():
    parser = argparse.ArgumentParser(prog="wimf", description="Encode, decode, inspect, and view WIMF images.")
    parser.add_argument("--version", action="version", version=f"WIMF {wimf.__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    encode = commands.add_parser("encode", aliases=["e"], help="encode a standard image as WIMF")
    encode.add_argument("input", help="source image")
    encode.add_argument("output", nargs="?", help="output path (default: source.wimf)")
    encode.add_argument("-q", "--quality", type=int, choices=range(1, 11), default=7)
    encode.add_argument("--lossless", action="store_true", help="preserve every source pixel exactly")
    encode.add_argument("--preset", choices=("Fast", "Balanced", "Extreme"), default="Balanced")
    encode.add_argument("--codec", choices=("auto", "raw", "predictive", "palette", "wavelet"), default="auto")
    encode.add_argument("--threads", type=_positive_int, help="worker count (default: conservative automatic value)")
    encode.add_argument("--anti-rot", action="store_true", help="add bounded corruption protection")
    encode.add_argument("--metadata", action="append", default=[], metavar="KEY=VALUE")
    encode.set_defaults(handler=_encode)

    decode = commands.add_parser("decode", aliases=["d"], help="decode WIMF to a standard image")
    decode.add_argument("input", help="source WIMF file")
    decode.add_argument("output", nargs="?", help="output path (default: source.png)")
    decode.add_argument("--roi", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"))
    decode.set_defaults(handler=_decode)

    thumbnail = commands.add_parser("thumbnail", help="render a bounded PNG thumbnail for desktop services")
    thumbnail.add_argument("input", help="source WIMF file")
    thumbnail.add_argument("output", help="output PNG path")
    thumbnail.add_argument("--size", type=_positive_int, default=256, help="maximum width and height")
    thumbnail.add_argument("--force", action="store_true")
    thumbnail.set_defaults(handler=_thumbnail)

    info = commands.add_parser("info", aliases=["i"], help="show image, tile, protection, and metadata details")
    info.add_argument("input")
    info.add_argument("--json", action="store_true")
    info.set_defaults(handler=_info)

    runtime = commands.add_parser("runtime", help="show the active codec backend")
    runtime.add_argument("--json", action="store_true")
    runtime.set_defaults(handler=_runtime)

    view = commands.add_parser("view", aliases=["v"], help="open the desktop viewer")
    view.add_argument("input", nargs="?")
    view.set_defaults(handler=_view)

    base64_parser = commands.add_parser("base64", help="convert WIMF to or from Base64 transport text")
    base64_commands = base64_parser.add_subparsers(dest="base64_command", required=True)
    base64_encode = base64_commands.add_parser("encode", help="encode a WIMF file as Base64")
    base64_encode.add_argument("input")
    base64_encode.add_argument("output", nargs="?", default="-")
    base64_encode.add_argument("--data-url", action="store_true")
    base64_encode.add_argument("--wrap", type=int, default=0)
    base64_encode.add_argument("--force", action="store_true")
    base64_encode.set_defaults(handler=_base64_encode)
    base64_decode = base64_commands.add_parser("decode", help="decode Base64 into a WIMF file")
    base64_decode.add_argument("input")
    base64_decode.add_argument("output")
    base64_decode.add_argument("--force", action="store_true")
    base64_decode.set_defaults(handler=_base64_decode)
    _add_base_transport(commands, "base16")
    _add_base_transport(commands, "base32")

    corrupt_parser = commands.add_parser("corrupt", help="write a deterministically corrupted WIM2 copy")
    corrupt_parser.add_argument("input")
    corrupt_parser.add_argument("output")
    corrupt_parser.add_argument("--seed", type=int, default=0)
    corrupt_parser.add_argument("--count", type=_positive_int, default=1)
    corrupt_parser.add_argument("--area", choices=AREAS, default="payload")
    corrupt_parser.add_argument("--tile", nargs=2, type=int, metavar=("X", "Y"))
    corrupt_parser.add_argument("--mutation", choices=("bit-flip", "overwrite", "truncate"), default="bit-flip")
    corrupt_parser.add_argument("--truncate", type=_positive_int, default=1)
    corrupt_parser.add_argument("--force", action="store_true")
    corrupt_parser.set_defaults(handler=_corrupt)

    diagnose_parser = commands.add_parser("diagnose", help="inspect corruption without weakening strict decode")
    diagnose_parser.add_argument("input")
    diagnose_parser.add_argument("--json", action="store_true")
    diagnose_parser.add_argument("--unsafe-preview")
    diagnose_parser.set_defaults(handler=_diagnose)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, TypeError, ValueError) as error:
        print(f"wimf: {error}", file=sys.stderr)
        print("Report reproducible bugs: https://github.com/benchware/WorstImageFormat/issues", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
