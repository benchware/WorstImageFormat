"""Strict corruption diagnostics and explicitly unsafe verified-tile previews."""

import random
import zlib

import numpy as np

from .api import WIMFDecoder
from .extensions import parse_extensions
from .hybrid import (
    ENTROPY_NONE,
    HEADER,
    MODE_NAMES,
    MODE_PALETTE,
    MODE_PREDICTIVE,
    MODE_RAW,
    _decompress,
    _palette_decode,
    _predictive_decode,
    _wavelet_decode,
    parse_v2,
    undo_channel_decorrelation,
)

AREAS = ("header", "metadata", "index", "payload", "extension", "parity")
MAX_PREVIEW_BYTES = 1024 * 1024 * 1024


def _ranges(data, area, tile=None):
    if area == "header":
        return [(0, min(HEADER.size, len(data)))]
    info = parse_v2(data)
    metadata_size = int.from_bytes(data[18:22], "little")
    index_start = HEADER.size + metadata_size
    index_end = index_start + len(info["entries"]) * 32
    if area == "metadata":
        return [(HEADER.size, index_start)]
    if area == "index":
        return [(index_start, index_end)]
    if area == "payload":
        entries = info["entries"]
        if tile is not None:
            entries = [entry for entry in entries if (entry[0], entry[1]) == tuple(tile)]
            if not entries:
                raise ValueError("requested WIM2 tile does not exist")
        return [(entry[8], entry[8] + entry[9]) for entry in entries]
    extensions = parse_extensions(data, verify_checksums=False)
    if area == "parity":
        parity = extensions.get(b"AROT")
        if parity is None:
            raise ValueError("WIM2 file has no anti-rot parity")
        return [(parity["offset"], parity["offset"] + parity["size"])]
    if area == "extension":
        return [(entry["offset"], entry["offset"] + entry["size"]) for entry in extensions.values()]
    raise ValueError(f"unknown corruption area {area!r}")


def corrupt(data, *, seed=0, count=1, area="payload", tile=None, mutation="bit-flip", truncate=1):
    """Return a deterministically damaged copy of WIM2 bytes."""
    source = bytes(data)
    if count < 1:
        raise ValueError("corruption count must be at least 1")
    if tile is not None and area != "payload":
        raise ValueError("tile targeting requires the payload area")
    ranges = [(start, end) for start, end in _ranges(source, area, tile) if end > start]
    population = sum(end - start for start, end in ranges)
    if not population:
        raise ValueError(f"WIM2 {area} area is empty")
    rng = random.Random(seed)
    damaged = bytearray(source)
    if mutation == "truncate":
        amount = max(1, int(truncate))
        if amount >= len(damaged):
            raise ValueError("truncation would remove the entire file")
        return bytes(damaged[:-amount])
    for _ in range(count):
        selected = rng.randrange(population)
        position = ranges[0][0]
        for start, end in ranges:
            length = end - start
            if selected < length:
                position = start + selected
                break
            selected -= length
        if mutation == "bit-flip":
            damaged[position] ^= 1 << rng.randrange(8)
        elif mutation == "overwrite":
            damaged[position] = rng.randrange(256)
        else:
            raise ValueError(f"unknown corruption mutation {mutation!r}")
    return bytes(damaged)


def diagnose(data):
    """Describe strict decode and per-tile checksum state without bypassing validation."""
    source = bytes(data)
    report = {"size": len(source), "strict_ok": False, "strict_error": None, "tiles": [], "extensions": {}}
    try:
        decoder = WIMFDecoder(source)
        decoder.decode()
        report.update({"strict_ok": True, "protected": decoder.was_protected, "repaired": decoder.was_repaired})
    except Exception as error:
        report["strict_error"] = str(error)
    try:
        info = parse_v2(source)
        report.update({key: info[key] for key in ("width", "height", "channels", "bit_depth", "tile_size")})
        for entry in info["entries"]:
            x, y, width, height, mode, _, _, _, offset, size, _, checksum = entry
            valid = (
                offset + size <= len(source) and (zlib.crc32(source[offset : offset + size]) & 0xFFFFFFFF) == checksum
            )
            report["tiles"].append(
                {"x": x, "y": y, "width": width, "height": height, "mode": MODE_NAMES[mode], "checksum_valid": valid}
            )
    except Exception as error:
        report["container_error"] = str(error)
    try:
        report["extensions"] = {
            kind.decode("ascii", "replace"): {"size": item["size"], "checksum_valid": item["checksum_valid"]}
            for kind, item in parse_extensions(source, verify_checksums=False).items()
        }
    except Exception as error:
        report["extension_error"] = str(error)
    return report


def unsafe_preview(data):
    """Decode checksum-valid WIM2 tiles and checkerboard every failed tile."""
    source = bytes(data)
    info = parse_v2(source)
    dtype = np.uint8 if info["bit_depth"] == 8 else np.dtype("<u2")
    output_bytes = info["width"] * info["height"] * info["channels"] * np.dtype(dtype).itemsize
    if output_bytes > MAX_PREVIEW_BYTES:
        raise ValueError("diagnostic preview exceeds the output safety limit")
    maximum = 255 if info["bit_depth"] == 8 else (1 << info["bit_depth"]) - 1
    output = np.zeros((info["height"], info["width"], info["channels"]), dtype=dtype)
    failed = []
    for entry in info["entries"]:
        x, y, width, height, mode, entropy, _, _, offset, size, raw_size, checksum = entry
        packed = source[offset : offset + size]
        try:
            if len(packed) != size or (zlib.crc32(packed) & 0xFFFFFFFF) != checksum:
                raise ValueError("checksum failure")
            raw = packed if entropy == ENTROPY_NONE else _decompress(packed, raw_size)
            if mode == MODE_RAW:
                tile = np.frombuffer(raw, dtype=dtype).reshape(height, width, info["channels"])
            elif mode == MODE_PREDICTIVE:
                tile = _predictive_decode(raw, height, width, info["channels"], dtype)
            elif mode == MODE_PALETTE:
                tile = _palette_decode(raw, height, width, info["channels"], dtype)
            else:
                tile = _wavelet_decode(raw, height, width, info["channels"], dtype)
            output[y : y + height, x : x + width] = tile
        except Exception as error:
            yy, xx = np.indices((height, width))
            checker = np.where(((xx // 8 + yy // 8) & 1)[..., None], maximum, 0).astype(dtype)
            output[y : y + height, x : x + width] = checker
            failed.append({"x": x, "y": y, "error": str(error)})
    output = undo_channel_decorrelation(output, info["channels"], info["bit_depth"], info["flags"])
    return output, failed
