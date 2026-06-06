import builtins as _builtins
from .io import loadImage, saveImage, stream_load
from .api import WIMFImage, WIMFDecoder, WIMFEncoder, open_image, edit_metadata as edit_meta

__version__ = "1.3.0"
__all__ = ["WIMFImage", "WIMFDecoder", "WIMFEncoder", "open", "save", "info", "edit_meta"]

def open(path):
    """High-level API to open and decode a WIMF file."""
    return open_image(path)

def info(path):
    """Lazily read headers and return WIMF metadata."""
    return WIMFDecoder(path).metadata

def save(path, image, **kwargs):
    """Convenience function to save any image-like object as WIMF."""
    raw = WIMFEncoder(image).encode(**kwargs)
    with _builtins.open(path, 'wb') as f:
        f.write(raw)

def is_wimf(source):
    """Fast check if a file or byte buffer is WIMF."""
    if isinstance(source, str):
        with open(source, 'rb') as f:
            return f.read(4) in [b"WIMF", b"AWIF"]
    return source[:4] in [b"WIMF", b"AWIF"]
