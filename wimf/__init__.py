import builtins as _builtins
from .io import loadImage, saveImage, stream_load
from .api import WIMFImage, WIMFDecoder, WIMFEncoder, open_image, edit_metadata as edit_meta

__version__ = "1.3.2"
__all__ = ["WIMFImage", "WIMFDecoder", "WIMFEncoder", "open", "save", "info", "edit_meta"]

def open(path):
    """High-level API to open and decode a WIMF file."""
    return open_image(path)

def info(path):
    """Lazily read headers and return WIMF metadata."""
    return WIMFDecoder(path).metadata

def save(path, image, **kwargs):
    """Convenience function to save any image-like object as WIMF."""
    encoder = WIMFEncoder(image)
    # Extract known metadata keys from kwargs
    meta_keys = ['author', 'copyright', 'desc', 'make', 'model', 'bit10', 'alpha', 'depth', 'is_animated']
    if 'anti_rot' in kwargs:
        encoder.set_anti_rot(kwargs['anti_rot'])
    
    meta_args = {k: v for k, v in kwargs.items() if k in meta_keys}
    if meta_args:
        encoder.set_metadata(**meta_args)
        
    # Remove meta keys from kwargs before passing to encode
    encode_args = {k: v for k, v in kwargs.items() if k not in meta_keys and k != 'anti_rot'}
    raw = encoder.encode(**encode_args)
    
    try:
        from . import wimf_cpp
        wimf_cpp.c_save_file(path, raw)
    except (ImportError, AttributeError):
        with _builtins.open(path, 'wb') as f:
            f.write(raw)

def is_wimf(source):
    """Fast check if a file or byte buffer is WIMF."""
    if isinstance(source, str):
        with _builtins.open(source, 'rb') as f:
            return f.read(4) in [b"WIMF", b"AWIF", b"ROT!"]
    return source[:4] in [b"WIMF", b"AWIF", b"ROT!"]
