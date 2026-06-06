import json
import struct
from .codec import encode_lossless, decode_lossless, encode_lossy, decode_lossy
from .animation import encode_animated, decode_animated

def loadImage(filename):
    with open(filename, 'rb') as f:
        header = f.read(4)
        if header not in [b"WIMF", b"AWIF"]: raise ValueError(f"Invalid Magic Byte: {header}")
        w, h = int.from_bytes(f.read(4), 'little'), int.from_bytes(f.read(4), 'little')
        flags = int.from_bytes(f.read(1), 'little')
        mlen = int.from_bytes(f.read(4), 'little')
        meta = json.loads(f.read(mlen).decode('utf-8')) if mlen > 0 else {}
        data = f.read()
        channels = meta.get('channels', 3)
        bit_depth = 10 if meta.get('bit10') else 8
        
        if header == b"AWIF":
            frames = decode_animated(data, w, h, channels)
            meta['is_animated'] = True
            return w, h, frames, meta
        if flags == 1: pix = decode_lossless(data, w, h, channels)
        elif flags in [5, 6, 8]: pix = decode_lossy(data, w, h, channels, bit_depth=bit_depth)
        else: pix = data
        return w, h, pix, meta

def saveImage(filename, w, h, pixels, compression=1, quality=5, metadata=None, preset="Balanced"):
    if metadata is None: metadata = {}
    is_animated = isinstance(pixels, list)
    bit_depth = 10 if metadata.get('bit10') else 8
    
    if is_animated:
        first_frame = pixels[0]
        if hasattr(first_frame, 'tobytes'):
            channels = first_frame.shape[-1] if len(first_frame.shape) == 3 else 1
            pixels = [f.tobytes() for f in pixels]
        else:
            div = (2 if bit_depth > 8 else 1)
            channels = len(first_frame) // (w * h * div)
    else:
        if hasattr(pixels, 'tobytes'):
            channels = pixels.shape[-1] if len(pixels.shape) == 3 else 1
            pixels = pixels.tobytes()
        else:
            div = (2 if bit_depth > 8 else 1)
            channels = len(pixels) // (w * h * div)
            
    metadata['channels'] = channels
    m_bytes = json.dumps(metadata).encode('utf-8')
    magic = b"AWIF" if is_animated else b"WIMF"
    
    if is_animated:
        data = encode_animated(pixels, w, h, channels, quality, preset)
        final_flags = 7
    else:
        if compression == 2:
            data = encode_lossy(pixels, w, h, quality=quality, preset=preset, channels=channels, bit_depth=bit_depth)
            final_flags = 8
        elif compression == 1:
            data = encode_lossless(pixels, w, h, channels)
            final_flags = 1
        else:
            data = pixels
            final_flags = 0
            
    with open(filename, 'wb') as f:
        f.write(magic)
        f.write(w.to_bytes(4, 'little') + h.to_bytes(4, 'little'))
        f.write(final_flags.to_bytes(1, 'little'))
        f.write(len(m_bytes).to_bytes(4, 'little') + m_bytes + data)
