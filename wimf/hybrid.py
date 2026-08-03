"""WIMF v2 hybrid, independently-decodable tile codec."""

import json
import os
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np

try:
    import zstandard as zstd
except ImportError:  # pragma: no cover - gives an actionable packaging error
    zstd = None

try:
    from . import wimf_v2_cpp as native
except ImportError:
    native = None


MAGIC = b"WIM2"
VERSION = 2
TILE_SIZE = 128
MAX_METADATA = 16 * 1024 * 1024
MAX_TILES = 16_777_216
HEADER = struct.Struct("<4sBBBBIIHII")
ENTRY = struct.Struct("<HHHHBBBBQIII")

MODE_RAW, MODE_PREDICTIVE, MODE_PALETTE, MODE_WAVELET = range(4)
ENTROPY_NONE, ENTROPY_ZSTD = range(2)
MODE_NAMES = {MODE_RAW: "raw", MODE_PREDICTIVE: "predictive", MODE_PALETTE: "palette", MODE_WAVELET: "wavelet"}
NAME_MODES = {v: k for k, v in MODE_NAMES.items()}


def _require_zstd():
    if zstd is None:
        raise RuntimeError("WIMF v2 requires the 'zstandard' package")


def _compress(data, preset):
    _require_zstd()
    level = {"Fast": 1, "Balanced": 7, "Extreme": 15}.get(preset, 7)
    return zstd.ZstdCompressor(level=level).compress(data)


def _decompress(data, expected):
    _require_zstd()
    if expected < 0 or expected > 1024 * 1024 * 1024:
        raise ValueError("invalid tile expansion size")
    try:
        return zstd.ZstdDecompressor().decompress(data, max_output_size=expected)
    except zstd.ZstdError as exc:
        raise ValueError(f"invalid zstd tile payload: {exc}") from exc


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _predictive_encode(tile):
    if native is not None:
        contiguous = np.ascontiguousarray(tile)
        return native.encode_predictive(contiguous, tile.shape[1], tile.shape[0], tile.shape[2], tile.dtype.itemsize)
    h, w, channels = tile.shape
    modulus = 256 if tile.dtype == np.uint8 else 65536
    out = bytearray()
    for c in range(channels):
        plane = tile[..., c].astype(np.int64)
        for y in range(h):
            candidates = []
            for kind in range(4):
                residual = np.empty(w, dtype=np.int64)
                for x in range(w):
                    left = int(plane[y, x - 1]) if x else 0
                    above = int(plane[y - 1, x]) if y else 0
                    corner = int(plane[y - 1, x - 1]) if x and y else 0
                    pred = (0, left, above, _paeth(left, above, corner))[kind]
                    residual[x] = (int(plane[y, x]) - pred) % modulus
                signed = np.where(residual >= modulus // 2, residual - modulus, residual)
                candidates.append((int(np.abs(signed).sum()), residual))
            kind = min(range(4), key=lambda k: candidates[k][0])
            out.append(kind)
            dtype = np.uint8 if modulus == 256 else np.dtype("<u2")
            out.extend(candidates[kind][1].astype(dtype).tobytes())
    return bytes(out)


def _predictive_decode(data, h, w, channels, dtype):
    if native is not None:
        raw = native.decode_predictive(data, w, h, channels, np.dtype(dtype).itemsize)
        return np.frombuffer(raw, dtype=dtype).reshape(h, w, channels).copy()
    modulus = 256 if dtype == np.uint8 else 65536
    sample_bytes = 1 if modulus == 256 else 2
    expected = channels * h * (1 + w * sample_bytes)
    if len(data) != expected:
        raise ValueError("invalid predictive tile length")
    out = np.zeros((h, w, channels), dtype=dtype)
    pos = 0
    for c in range(channels):
        for y in range(h):
            kind = data[pos]
            pos += 1
            if kind > 3:
                raise ValueError("invalid predictor id")
            residual = np.frombuffer(data, dtype=np.uint8 if sample_bytes == 1 else "<u2", count=w, offset=pos)
            pos += w * sample_bytes
            for x in range(w):
                left = int(out[y, x - 1, c]) if x else 0
                above = int(out[y - 1, x, c]) if y else 0
                corner = int(out[y - 1, x - 1, c]) if x and y else 0
                pred = (0, left, above, _paeth(left, above, corner))[kind]
                out[y, x, c] = (pred + int(residual[x])) % modulus
    return out


def _palette_encode(tile):
    if native is not None:
        packed = native.encode_palette(
            np.ascontiguousarray(tile), tile.shape[1], tile.shape[0], tile.shape[2], tile.dtype.itemsize
        )
        return packed or None
    flat = tile.reshape(-1, tile.shape[2])
    palette, indices = np.unique(flat, axis=0, return_inverse=True)
    if len(palette) > 256:
        return None
    return struct.pack("<H", len(palette)) + palette.tobytes() + indices.astype(np.uint8).tobytes()


def _palette_decode(data, h, w, channels, dtype):
    if native is not None:
        raw = native.decode_palette(data, w, h, channels, np.dtype(dtype).itemsize)
        return np.frombuffer(raw, dtype=dtype).reshape(h, w, channels).copy()
    if len(data) < 2:
        raise ValueError("truncated palette tile")
    count = struct.unpack_from("<H", data)[0]
    if not 1 <= count <= 256:
        raise ValueError("invalid palette size")
    sample_bytes = np.dtype(dtype).itemsize
    pbytes = count * channels * sample_bytes
    if len(data) != 2 + pbytes + h * w:
        raise ValueError("invalid palette tile length")
    palette = np.frombuffer(data, dtype=dtype, count=count * channels, offset=2).reshape(count, channels)
    indices = np.frombuffer(data, dtype=np.uint8, count=h * w, offset=2 + pbytes)
    if indices.size and int(indices.max()) >= count:
        raise ValueError("palette index out of range")
    return palette[indices].reshape(h, w, channels).copy()


def _lift53_forward(line):
    x = line.astype(np.int64).copy()
    even, odd = x[0::2].copy(), x[1::2].copy()
    odd -= (even + np.r_[even[1:], even[-1]]) // 2
    even += (np.r_[odd[0], odd[:-1]] + odd + 2) // 4
    return np.concatenate((even, odd))


def _lift53_inverse(line):
    n = len(line)
    half = (n + 1) // 2
    even, odd = line[:half].astype(np.int64).copy(), line[half:].astype(np.int64).copy()
    even -= (np.r_[odd[0], odd[:-1]] + odd + 2) // 4
    odd += (even + np.r_[even[1:], even[-1]]) // 2
    out = np.empty(n, dtype=np.int64)
    out[0::2], out[1::2] = even, odd
    return out


def _lift97_forward(line):
    a, b, g, d, k = -1.586134342, -0.05298011854, 0.8829110762, 0.4435068522, 1.149604398
    even, odd = line[0::2].astype(np.float64).copy(), line[1::2].astype(np.float64).copy()
    odd += a * (even + np.r_[even[1:], even[-1]])
    even += b * (np.r_[odd[0], odd[:-1]] + odd)
    odd += g * (even + np.r_[even[1:], even[-1]])
    even += d * (np.r_[odd[0], odd[:-1]] + odd)
    even *= k
    odd /= k
    return np.concatenate((even, odd))


def _lift97_inverse(line):
    a, b, g, d, k = -1.586134342, -0.05298011854, 0.8829110762, 0.4435068522, 1.149604398
    n = len(line)
    half = (n + 1) // 2
    even, odd = line[:half].astype(np.float64).copy(), line[half:].astype(np.float64).copy()
    even /= k
    odd *= k
    even -= d * (np.r_[odd[0], odd[:-1]] + odd)
    odd -= g * (even + np.r_[even[1:], even[-1]])
    even -= b * (np.r_[odd[0], odd[:-1]] + odd)
    odd -= a * (even + np.r_[even[1:], even[-1]])
    out = np.empty(n, dtype=np.float64)
    out[0::2], out[1::2] = even, odd
    return out


def _wavelet_forward_2d(a, levels, reversible):
    out = a.astype(np.int64 if reversible else np.float64).copy()
    h, w = out.shape
    transform = _lift53_forward if reversible else _lift97_forward
    for _ in range(levels):
        for y in range(h):
            out[y, :w] = transform(out[y, :w])
        for x in range(w):
            out[:h, x] = transform(out[:h, x])
        h //= 2
        w //= 2
    return out


def _wavelet_inverse_2d(a, levels, reversible):
    out = a.astype(np.int64 if reversible else np.float64).copy()
    full_h, full_w = out.shape
    transform = _lift53_inverse if reversible else _lift97_inverse
    for level in range(levels - 1, -1, -1):
        h, w = full_h >> level, full_w >> level
        for x in range(w):
            out[:h, x] = transform(out[:h, x])
        for y in range(h):
            out[y, :w] = transform(out[y, :w])
    return out


def _varints_encode(values):
    out = bytearray()
    run = 0
    for value in values:
        value = int(value)
        if value == 0:
            run += 1
            continue
        out.append(0)
        n = run
        while n >= 0x80:
            out.append((n & 0x7F) | 0x80)
            n >>= 7
        out.append(n)
        run = 0
        zz = (value << 1) ^ (value >> 63)
        while zz >= 0x80:
            out.append((zz & 0x7F) | 0x80)
            zz >>= 7
        out.append(zz)
    if run:
        out.append(0)
        n = run
        while n >= 0x80:
            out.append((n & 0x7F) | 0x80)
            n >>= 7
        out.append(n)
    return bytes(out)


def _read_varint(data, pos):
    value = shift = 0
    for _ in range(10):
        if pos >= len(data):
            raise ValueError("truncated coefficient varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7
    raise ValueError("oversized coefficient varint")


def _varints_decode(data, count):
    values = np.zeros(count, dtype=np.int64)
    pos = index = 0
    while index < count:
        marker = data[pos] if pos < len(data) else None
        if marker != 0:
            raise ValueError("invalid coefficient marker")
        pos += 1
        run, pos = _read_varint(data, pos)
        if run > count - index:
            raise ValueError("coefficient zero run exceeds tile")
        index += run
        if index == count:
            break
        zz, pos = _read_varint(data, pos)
        values[index] = (zz >> 1) ^ -(zz & 1)
        index += 1
    if pos != len(data):
        raise ValueError("trailing coefficient data")
    return values


def _wavelet_encode(tile, quality, lossless):
    h, w, channels = tile.shape
    ph = 1 << int(np.ceil(np.log2(max(2, h))))
    pw = 1 << int(np.ceil(np.log2(max(2, w))))
    levels = min(3, int(np.log2(min(ph, pw))))
    q = 1.0 if lossless else max(1.0, (11 - quality) * 1.5)
    chunks = [struct.pack("<HHBBf", ph, pw, levels, int(lossless), q)]
    for c in range(channels):
        padded = np.pad(tile[..., c], ((0, ph - h), (0, pw - w)), mode="symmetric")
        if native is not None:
            coeff = np.asarray(
                native.wavelet_forward(np.ascontiguousarray(padded), pw, ph, padded.dtype.itemsize, lossless, levels, q)
            )
        else:
            coeff = np.rint(_wavelet_forward_2d(padded, levels, lossless) / q).astype(np.int64)
        packed = _varints_encode(coeff.ravel())
        chunks.append(struct.pack("<I", len(packed)))
        chunks.append(packed)
    return b"".join(chunks)


def _wavelet_decode(data, h, w, channels, dtype):
    if len(data) < 10:
        raise ValueError("truncated wavelet tile")
    ph, pw, levels, reversible, q = struct.unpack_from("<HHBBf", data)
    if (
        ph > 256
        or pw > 256
        or ph < h
        or pw < w
        or not 0 <= levels <= 8
        or reversible not in (0, 1)
        or not np.isfinite(q)
        or q <= 0
    ):
        raise ValueError("invalid wavelet dimensions")
    pos = 10
    planes = []
    max_value = np.iinfo(dtype).max
    for _ in range(channels):
        if pos + 4 > len(data):
            raise ValueError("truncated wavelet channel")
        size = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if pos + size > len(data):
            raise ValueError("truncated wavelet coefficients")
        coeff = _varints_decode(data[pos : pos + size], ph * pw).reshape(ph, pw)
        pos += size
        if native is not None:
            decoded = native.wavelet_inverse(
                np.ascontiguousarray(coeff), pw, ph, np.dtype(dtype).itemsize, bool(reversible), levels, q
            )
            plane = np.frombuffer(decoded, dtype=dtype).reshape(ph, pw)[:h, :w]
        else:
            plane = _wavelet_inverse_2d(coeff * q, levels, bool(reversible))[:h, :w]
        planes.append(np.clip(np.rint(plane), 0, max_value).astype(dtype))
    if pos != len(data):
        raise ValueError("trailing wavelet tile data")
    return np.stack(planes, axis=2)


def _classify(tile):
    if native is not None:
        ranked = int(
            native.classify(
                np.ascontiguousarray(tile), tile.shape[1], tile.shape[0], tile.shape[2], tile.dtype.itemsize
            )
        )
        if ranked == MODE_PALETTE:
            return [MODE_PALETTE, MODE_PREDICTIVE]
        if ranked == MODE_PREDICTIVE:
            return [MODE_PREDICTIVE, MODE_WAVELET]
        return [MODE_WAVELET, MODE_PREDICTIVE]
    flat = tile.reshape(-1, tile.shape[2])
    unique = len(np.unique(flat, axis=0)) if flat.shape[0] <= 16384 else 257
    gray = tile[..., : min(3, tile.shape[2])].astype(np.float64).mean(axis=2)
    vertical = np.abs(np.diff(gray, axis=0)).mean() if gray.shape[0] > 1 else 0.0
    horizontal = np.abs(np.diff(gray, axis=1)).mean() if gray.shape[1] > 1 else 0.0
    edge = (vertical + horizontal) / 2
    variance = float(gray.var())
    if unique <= 256:
        return [MODE_PALETTE, MODE_PREDICTIVE]
    if edge > 25 and variance < 5000:
        return [MODE_PREDICTIVE, MODE_WAVELET]
    return [MODE_WAVELET, MODE_PREDICTIVE]


def _candidate_modes(tile, codec, preset):
    if codec != "auto":
        return [NAME_MODES[codec], MODE_RAW]
    ranked = _classify(tile)
    if preset == "Fast":
        return [ranked[0], MODE_RAW]
    if preset == "Extreme":
        return [MODE_PALETTE, MODE_PREDICTIVE, MODE_WAVELET, MODE_RAW]
    return ranked + [MODE_RAW]


def encode_v2(
    pixels,
    width,
    height,
    channels,
    bit_depth=8,
    quality=7,
    lossless=False,
    preset="Balanced",
    codec="auto",
    metadata=None,
    tile_size=TILE_SIZE,
    threads=None,
):
    if codec not in NAME_MODES and codec != "auto":
        raise ValueError(f"unknown codec {codec!r}")
    if not 1 <= quality <= 10:
        raise ValueError("quality must be between 1 and 10")
    if bit_depth not in (8, 10, 16):
        raise ValueError("bit_depth must be 8, 10, or 16")
    if not 16 <= tile_size <= 256:
        raise ValueError("tile_size must be between 16 and 256")
    dtype = np.uint8 if bit_depth == 8 else np.dtype("<u2")
    image = np.frombuffer(pixels, dtype=dtype).reshape(height, width, channels)
    meta = dict(metadata or {})
    meta.update({"channels": channels, "bit_depth": bit_depth, "format_version": 2})
    meta_bytes = json.dumps(meta, separators=(",", ":")).encode()
    flags = 1 if lossless else 0
    coordinates = [(x, y) for y in range(0, height, tile_size) for x in range(0, width, tile_size)]

    def encode_tile(position):
        x, y = position
        tile = image[y : y + tile_size, x : x + tile_size]
        candidates = []
        for mode in _candidate_modes(tile, codec, preset):
            if mode == MODE_RAW:
                raw = tile.tobytes()
            elif mode == MODE_PALETTE:
                raw = _palette_encode(tile)
                if raw is None:
                    continue
            elif mode == MODE_PREDICTIVE:
                raw = _predictive_encode(tile)
            else:
                raw = _wavelet_encode(tile, quality, lossless)
            packed = raw if mode == MODE_RAW else _compress(raw, preset)
            reconstructed = tile if lossless or mode != MODE_WAVELET else _wavelet_decode(raw, *tile.shape, dtype)
            distortion = float(np.mean((tile.astype(np.float64) - reconstructed.astype(np.float64)) ** 2))
            score = len(packed) if lossless else len(packed) + distortion * tile.size / max(1, quality * 64)
            candidates.append((score, len(packed), mode, raw, packed))
        _, _, mode, raw, packed = min(candidates)
        entropy = ENTROPY_NONE if mode == MODE_RAW else ENTROPY_ZSTD
        return [x, y, tile.shape[1], tile.shape[0], mode, entropy, 1, raw, packed]

    worker_count = min(os.cpu_count() or 1, 8) if threads is None else int(threads)
    if worker_count < 1:
        raise ValueError("threads must be at least 1")
    if worker_count == 1 or len(coordinates) == 1:
        tiles = [encode_tile(position) for position in coordinates]
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            tiles = list(executor.map(encode_tile, coordinates))
    if native is not None and hasattr(native, "write_container"):
        native_tiles = [
            (x, y, tw, th, mode, entropy, layers, len(raw), packed)
            for x, y, tw, th, mode, entropy, layers, raw, packed in tiles
        ]
        return native.write_container(flags, bit_depth, channels, width, height, tile_size, meta_bytes, native_tiles)
    header_size = HEADER.size + len(meta_bytes) + len(tiles) * ENTRY.size
    entries = bytearray()
    payload = bytearray()
    offset = header_size
    for x, y, tw, th, mode, entropy, layers, raw, packed in tiles:
        entries.extend(
            ENTRY.pack(x, y, tw, th, mode, entropy, layers, 0, offset, len(packed), len(raw), zlib.crc32(packed))
        )
        payload.extend(packed)
        offset += len(packed)
    return (
        HEADER.pack(MAGIC, VERSION, flags, bit_depth, channels, width, height, tile_size, len(meta_bytes), len(tiles))
        + meta_bytes
        + entries
        + payload
    )


def parse_v2(data):
    if native is not None and hasattr(native, "inspect_container"):
        try:
            inspected = native.inspect_container(bytes(data))
        except (RuntimeError, TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        try:
            metadata_bytes = bytes(inspected["metadata"])
            inspected["metadata"] = json.loads(metadata_bytes.decode()) if metadata_bytes else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid WIMF v2 metadata") from exc
        return inspected
    if len(data) < HEADER.size:
        raise ValueError("file too short for WIMF v2 header")
    magic, version, flags, depth, channels, width, height, tile_size, mlen, count = HEADER.unpack_from(data)
    if magic != MAGIC or version != VERSION:
        raise ValueError("not a supported WIMF v2 file")
    if not width or not height or not 1 <= channels <= 16 or depth not in (8, 10, 16) or not 16 <= tile_size <= 256:
        raise ValueError("invalid WIMF v2 image properties")
    if mlen > MAX_METADATA or count > MAX_TILES:
        raise ValueError("WIMF v2 header limits exceeded")
    index_start = HEADER.size + mlen
    data_start = index_start + count * ENTRY.size
    if data_start > len(data):
        raise ValueError("truncated WIMF v2 metadata or tile index")
    try:
        meta = json.loads(data[HEADER.size : index_start].decode()) if mlen else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid WIMF v2 metadata") from exc
    entries = []
    expected_count = ((width + tile_size - 1) // tile_size) * ((height + tile_size - 1) // tile_size)
    if count != expected_count:
        raise ValueError("WIMF v2 tile count does not cover the image")
    seen = set()
    for i in range(count):
        entry = ENTRY.unpack_from(data, index_start + i * ENTRY.size)
        x, y, tw, th, mode, entropy, layers, _, offset, size, raw_size, crc = entry
        if not tw or not th or x + tw > width or y + th > height or mode not in MODE_NAMES or entropy not in (0, 1):
            raise ValueError("invalid WIMF v2 tile index entry")
        if offset < data_start or offset + size > len(data):
            raise ValueError("WIMF v2 tile points outside file")
        if (
            (x, y) in seen
            or x % tile_size
            or y % tile_size
            or tw != min(tile_size, width - x)
            or th != min(tile_size, height - y)
        ):
            raise ValueError("invalid or duplicate WIMF v2 tile geometry")
        max_raw = max(1_048_576, tw * th * channels * max(2, depth // 8) * 32)
        if raw_size > max_raw:
            raise ValueError("WIMF v2 tile expansion is excessive")
        seen.add((x, y))
        entries.append(entry)
    return {
        "flags": flags,
        "bit_depth": depth,
        "channels": channels,
        "width": width,
        "height": height,
        "tile_size": tile_size,
        "metadata": meta,
        "entries": entries,
    }


def decode_v2(data, roi=None, target_layer=2):
    info = parse_v2(data)
    dtype = np.uint8 if info["bit_depth"] == 8 else np.dtype("<u2")
    if roi is None:
        rx, ry, rw, rh = 0, 0, info["width"], info["height"]
    else:
        rx, ry, rw, rh = map(int, roi)
        if rx < 0 or ry < 0 or rw <= 0 or rh <= 0 or rx + rw > info["width"] or ry + rh > info["height"]:
            raise ValueError("ROI is outside image")
    out = np.zeros((rh, rw, info["channels"]), dtype=dtype)
    for entry in info["entries"]:
        x, y, tw, th, mode, entropy, _, _, offset, size, raw_size, crc = entry
        if x >= rx + rw or y >= ry + rh or x + tw <= rx or y + th <= ry:
            continue
        packed = data[offset : offset + size]
        if zlib.crc32(packed) != crc:
            raise ValueError("WIMF v2 tile checksum mismatch")
        raw = packed if entropy == ENTROPY_NONE else _decompress(packed, raw_size)
        if len(raw) != raw_size:
            raise ValueError("WIMF v2 tile expansion length mismatch")
        if mode == MODE_RAW:
            expected = tw * th * info["channels"] * np.dtype(dtype).itemsize
            if len(raw) != expected:
                raise ValueError("invalid raw tile length")
            tile = np.frombuffer(raw, dtype=dtype).reshape(th, tw, info["channels"])
        elif mode == MODE_PREDICTIVE:
            tile = _predictive_decode(raw, th, tw, info["channels"], dtype)
        elif mode == MODE_PALETTE:
            tile = _palette_decode(raw, th, tw, info["channels"], dtype)
        else:
            tile = _wavelet_decode(raw, th, tw, info["channels"], dtype)
        sx0, sy0 = max(rx, x), max(ry, y)
        sx1, sy1 = min(rx + rw, x + tw), min(ry + rh, y + th)
        out[sy0 - ry : sy1 - ry, sx0 - rx : sx1 - rx] = tile[sy0 - y : sy1 - y, sx0 - x : sx1 - x]
    return out.tobytes(), info
