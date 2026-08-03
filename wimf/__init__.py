import builtins as _builtins
import os

from .api import WIMFDecoder, WIMFEncoder, WIMFImage, open_image
from .api import edit_metadata as edit_meta
from .io import loadImage, saveImage, stream_load

__version__ = "2.0.0"
__all__ = [
    "WIMFImage",
    "WIMFDecoder",
    "WIMFEncoder",
    "open",
    "save",
    "info",
    "edit_meta",
    "loadImage",
    "saveImage",
    "stream_load",
    "runtime_info",
]


def open(path):
    """High-level API to open and decode a WIMF file."""
    return open_image(path)


def info(path):
    """Lazily read headers and return WIMF metadata."""
    return WIMFDecoder(path).metadata


def save(path, image, **kwargs):
    """Convenience function to save any image-like object as WIMF."""
    encoder = WIMFEncoder(image)
    # Keys that control encoding behaviour (passed to encode())
    encode_keys = {"quality", "preset", "lossless", "format_version", "codec", "threads"}

    if "anti_rot" in kwargs:
        encoder.set_anti_rot(kwargs["anti_rot"])

    # Any kwarg that is neither an encode arg nor anti_rot goes into metadata
    meta_args = {k: v for k, v in kwargs.items() if k not in encode_keys and k != "anti_rot"}
    if meta_args:
        encoder.set_metadata(**meta_args)

    encode_args = {k: v for k, v in kwargs.items() if k in encode_keys}
    raw = encoder.encode(**encode_args)

    try:
        from .wimf_cpp import c_save_file

        c_save_file(os.fspath(path), raw)
    except (ImportError, AttributeError):
        with _builtins.open(path, "wb") as f:
            f.write(raw)


def is_wimf(source):
    """Fast check if a file or byte buffer is WIMF."""
    if isinstance(source, str):
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
        }
    details = dict(native_info())
    details["native"] = True
    details["effective_threads"] = min(int(details["hardware_threads"]), 8)
    details["zstandard_version"] = zstd_version
    return details
