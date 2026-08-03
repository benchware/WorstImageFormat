import builtins as _builtins
import os

from .api import WIMFDecoder, WIMFEncoder, WIMFImage
from .api import edit_metadata as edit_meta
from .io import loadImage, saveImage, stream_load

__version__ = "2.1.0"
__all__ = [
    "WIMFImage",
    "WIMFDecoder",
    "WIMFEncoder",
    "open",
    "decode",
    "encode",
    "save",
    "info",
    "inspect",
    "edit_meta",
    "loadImage",
    "saveImage",
    "stream_load",
    "runtime_info",
    "to_base64",
    "from_base64",
    "to_data_url",
    "from_data_url",
    "compare",
    "rewrite_metadata",
    "operation_token",
]

from .transport import from_base64, from_data_url, to_base64, to_data_url


class _PythonOperationToken:
    def __init__(self):
        import threading

        self._event = threading.Event()
        self.completed = 0
        self.total = 0
        self.stage = ""

    @property
    def cancelled(self):
        return self._event.is_set()

    def cancel(self):
        self._event.set()

    def reset(self):
        self._event.clear()
        self.completed = self.total = 0
        self.stage = ""


def operation_token():
    """Create a progress/cancellation token accepted by native WIM2 operations."""
    try:
        from .wimf_v2_cpp import OperationToken

        return OperationToken()
    except ImportError:
        return _PythonOperationToken()


def compare(first, second, *, bit_depth=None):
    """Compare equally shaped image arrays and return native metrics plus a difference array."""
    import math

    import numpy as np

    left, right = np.asarray(first), np.asarray(second)
    if left.ndim == 2:
        left = left[..., None]
    if right.ndim == 2:
        right = right[..., None]
    if left.shape != right.shape or left.dtype != right.dtype or left.dtype not in (np.dtype("uint8"), np.dtype("uint16")):
        raise ValueError("comparison images must have matching uint8 or uint16 shape and dtype")
    depth = int(bit_depth or (8 if left.dtype == np.uint8 else 16))
    try:
        from . import wimf_v2_cpp

        result = dict(
            wimf_v2_cpp.compare_images(
                np.ascontiguousarray(left), np.ascontiguousarray(right), left.shape[1], left.shape[0], left.shape[2], depth
            )
        )
        result["difference"] = np.frombuffer(result["difference"], dtype=left.dtype).reshape(left.shape).copy()
        return result
    except (ImportError, AttributeError):
        delta = np.abs(left.astype(np.int64) - right.astype(np.int64))
        mse = float(np.mean(delta.astype(np.float64) ** 2))
        peak = (1 << depth) - 1
        return {
            "difference": delta.astype(left.dtype),
            "mse": mse,
            "maximum_error": int(delta.max(initial=0)),
            "psnr": math.inf if mse == 0 else 10 * math.log10(peak * peak / mse),
        }


def rewrite_metadata(source, metadata):
    """Rewrite WIM2 metadata without recompressing any tile payload."""
    import json
    import struct
    import zlib

    from .extensions import append_extensions, encode_anti_rot, parse_extensions
    from .hybrid import ENTRY, HEADER, MAX_METADATA, parse_v2

    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")
    decoder = WIMFDecoder(source)
    if decoder.magic != b"WIM2":
        raise ValueError("non-recompressing metadata edits require WIM2")
    data = decoder._raw
    info = parse_v2(data)
    updated = dict(metadata)
    updated.update({"channels": info["channels"], "bit_depth": info["bit_depth"], "format_version": 2})
    metadata_bytes = json.dumps(updated, separators=(",", ":")).encode("utf-8")
    if len(metadata_bytes) > MAX_METADATA:
        raise ValueError("metadata exceeds the WIM2 safety limit")
    extensions = parse_extensions(data)
    try:
        from . import wimf_v2_cpp

        base = bytes(wimf_v2_cpp.rewrite_metadata(data, metadata_bytes))
    except (ImportError, AttributeError):
        entries = info["entries"]
        base_size = HEADER.size + len(metadata_bytes) + len(entries) * ENTRY.size
        index = bytearray()
        payload = bytearray()
        offset = base_size
        for entry in entries:
            x, y, width, height, mode, entropy, layers, reserved, old_offset, size, raw_size, checksum = entry
            packed = data[old_offset : old_offset + size]
            if len(packed) != size or (zlib.crc32(packed) & 0xFFFFFFFF) != checksum:
                raise ValueError("cannot rewrite metadata in a corrupted WIM2 file")
            index.extend(ENTRY.pack(x, y, width, height, mode, entropy, layers, reserved, offset, size, raw_size, checksum))
            payload.extend(packed)
            offset += size
        base = HEADER.pack(
            b"WIM2", 2, info["flags"], info["bit_depth"], info["channels"], info["width"], info["height"],
            info["tile_size"], len(metadata_bytes), len(entries)
        ) + metadata_bytes + index + payload
    chunks = [(kind, item["payload"], item["flags"]) for kind, item in extensions.items() if kind != b"AROT"]
    if b"AROT" in extensions:
        protected_prefix = base + b"".join(chunk for _, chunk, _ in chunks)
        chunks.append((b"AROT", encode_anti_rot(protected_prefix), extensions[b"AROT"]["flags"]))
    return append_extensions(base, chunks) if chunks else base


def decode(source, *, roi=None, target_layer=2, mip_level=0, operation_token=None):
    """Decode a path, bytes object, or binary stream into a :class:`WIMFImage`."""
    return WIMFDecoder(source).decode(
        roi=roi, target_layer=target_layer, mip_level=mip_level, operation_token=operation_token
    )


def open(path, **kwargs):
    """Open and decode a WIMF file. This is an alias for :func:`decode`."""
    return decode(path, **kwargs)


def info(path):
    """Return metadata only. Use :func:`inspect` for complete file details."""
    return WIMFDecoder(path).metadata


def inspect(source):
    """Return a plain dictionary describing a WIMF container without decoding pixels."""
    decoder = WIMFDecoder(source)
    result = {
        "format": decoder.magic.decode("ascii", "replace"),
        "width": decoder.width,
        "height": decoder.height,
        "channels": decoder.channels,
        "bit_depth": decoder.bit_depth,
        "protected": decoder.was_protected,
        "repaired": decoder.was_repaired,
        "history_states": decoder.num_states,
        "metadata": dict(decoder.metadata),
    }
    if decoder.magic == b"WIM2":
        from .hybrid import MODE_NAMES, parse_v2

        parsed = parse_v2(decoder._raw)
        counts = {name: 0 for name in MODE_NAMES.values()}
        for entry in parsed["entries"]:
            counts[MODE_NAMES[entry[4]]] += 1
        result.update({"tile_size": parsed["tile_size"], "tile_modes": counts})
    return result


def encode(image, **kwargs):
    """Encode a Pillow image, NumPy array, or :class:`WIMFImage` to bytes.

    Common options are ``quality``, ``lossless``, ``preset``, ``codec``, and
    ``threads``. Pass application metadata through ``metadata={...}``.
    """
    encoder = WIMFEncoder(image)
    encode_keys = {"quality", "preset", "lossless", "format_version", "codec", "threads", "operation_token"}
    encoder.set_anti_rot(bool(kwargs.pop("anti_rot", False)))
    supplied_metadata = kwargs.pop("metadata", None)
    if supplied_metadata is not None and not isinstance(supplied_metadata, dict):
        raise TypeError("metadata must be a dictionary")
    meta_args = dict(supplied_metadata or {})
    # Preserve the historical convenience of accepting metadata as extra keywords.
    meta_args.update({k: v for k, v in kwargs.items() if k not in encode_keys})
    if meta_args:
        encoder.set_metadata(**meta_args)
    encode_args = {k: v for k, v in kwargs.items() if k in encode_keys}
    return encoder.encode(**encode_args)


def save(path, image, **kwargs):
    """Encode an image and write it to ``path``. Returns the output path."""
    raw = encode(image, **kwargs)

    try:
        from .wimf_cpp import c_save_file

        c_save_file(os.fspath(path), raw)
    except (ImportError, AttributeError):
        with _builtins.open(path, "wb") as f:
            f.write(raw)
    return os.fspath(path)


def is_wimf(source):
    """Fast check if a file or byte buffer is WIMF."""
    if isinstance(source, (str, os.PathLike)):
        with _builtins.open(source, "rb") as f:
            return f.read(4) in [b"WIMF", b"WIM2", b"AWIF", b"ROT!"]
    return source[:4] in [b"WIMF", b"WIM2", b"AWIF", b"ROT!"]


def runtime_info():
    """Return details about the active WIMF v2 processing backend."""
    import os
    import platform

    try:
        import zstandard

        zstd_version = zstandard.__version__
    except (ImportError, AttributeError):
        zstd_version = "unavailable"

    try:
        from .wimf_v2_cpp import runtime_info as native_info
    except ImportError:
        return {
            "native": False,
            "architecture": platform.machine().lower() or "unknown",
            "simd": "python",
            "hardware_threads": os.cpu_count() or 1,
            "effective_threads": min(os.cpu_count() or 1, 8),
            "codec_version": "2.1-python",
            "zstandard_version": zstd_version,
            "native_orchestration": False,
            "execution_policies": ("python-threaded",),
        }
    details = dict(native_info())
    details["native"] = True
    details["effective_threads"] = min(int(details["hardware_threads"]), 8)
    details.setdefault("zstandard_version", zstd_version)
    details["python_zstandard_version"] = zstd_version
    return details
