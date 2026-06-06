import os
import json
import struct
import base64
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

from .io import loadImage, saveImage, stream_load
from .codec import encode_lossy, decode_lossy, encode_lossless, decode_lossless
from .meta_tool import surgical_read, surgical_write

class WIMFImage:
    """
    High-level WIMF Image object that encapsulates pixel data and WIMF-specific metadata.
    Acts as a bridge between the WIMF codec and standard imaging libraries.
    """
    def __init__(self, pil_image, metadata=None):
        self.pil = pil_image
        self.metadata = metadata or {}
        
    @property
    def width(self): return self.pil.width
    
    @property
    def height(self): return self.pil.height
    
    @property
    def size(self): return self.pil.size
    
    @property
    def mode(self): return self.pil.mode
    
    @property
    def depth_map(self):
        """Returns the embedded depth map as a numpy array if present."""
        if not self.metadata.get('depth'): return None
        # Depth is packed as the last channel
        arr = np.array(self.pil)
        return arr[..., -1]

    def show(self):
        self.pil.show()
        
    def to_numpy(self):
        """Convert to a standard NumPy array."""
        return np.array(self.pil)
        
    def to_opencv(self):
        """Convert to OpenCV format (BGR)."""
        arr = np.array(self.pil.convert('RGB'))
        return arr[:, :, ::-1]

class WIMFDecoder:
    """
    Enterprise-grade WIMF Decoder. Support lazy header parsing, 
    targeted ROI decoding, and asynchronous execution.
    """
    def __init__(self, source):
        """
        Initialize the decoder. 
        :param source: File path, file-like object, or bytes.
        """
        if isinstance(source, (str, bytes, os.PathLike)):
            if isinstance(source, bytes):
                self._buffer = io.BytesIO(source)
            else:
                self._buffer = open(source, 'rb')
        else:
            self._buffer = source
            
        self._parse_header()
        
    @classmethod
    def from_base64(cls, b64_str):
        """Initialize from a Base64 string (ideal for JSON APIs)."""
        return cls(base64.b64decode(b64_str))

    def _parse_header(self):
        self._buffer.seek(0)
        magic = self._buffer.read(4)
        if magic not in [b"WIMF", b"AWIF"]:
            raise ValueError("Invalid WIMF/AWIF magic bytes")
        self.magic = magic
        self.width = int.from_bytes(self._buffer.read(4), 'little')
        self.height = int.from_bytes(self._buffer.read(4), 'little')
        self.flags = int.from_bytes(self._buffer.read(1), 'little')
        mlen = int.from_bytes(self._buffer.read(4), 'little')
        self.metadata = json.loads(self._buffer.read(mlen).decode('utf-8'))
        self._data_start = self._buffer.tell()
        
        self.channels = self.metadata.get('channels', 3)
        self.bit_depth = 10 if self.metadata.get('bit10') else 8
        self.is_animated = (magic == b"AWIF")

    def decode(self, roi=None, target_layer=2):
        """
        Synchronously decode the image.
        :param roi: Optional tuple (x, y, w, h) for Region of Interest decoding.
        :param target_layer: Progressive layer to stop at (0, 1, or 2).
        :return: WIMFImage object.
        """
        self._buffer.seek(self._data_start)
        data = self._buffer.read()
        
        # Call low-level codec
        if self.magic == b"AWIF":
            from .animation import decode_animated
            frames = decode_animated(data, self.width, self.height, self.channels, bit_depth=self.bit_depth)
            # For simplicity, high-level API returns first frame of animation as primary image
            pix = frames[0]
        elif self.flags == 1:
            pix = decode_lossless(data, self.width, self.height, self.channels)
        else:
            pix = decode_lossy(data, self.width, self.height, self.channels, 
                              bit_depth=self.bit_depth, target_layer=target_layer, roi=roi)
            
        w, h = self.width, self.height
        if roi:
            _, _, w, h = roi
            
        # Handle 10-bit downsampling for standard PIL viewing
        if self.bit_depth == 10:
            arr = np.frombuffer(pix, dtype=np.uint16).reshape((h, w, self.channels))
            pix = (arr >> 2).astype(np.uint8).tobytes()
            
        mode = 'RGBA' if self.channels >= 4 else 'RGB'
        # If we have a depth map, PIL might not like 5 channels, so we strip it for the primary view
        if self.metadata.get('depth') and self.channels == 5:
            arr = np.frombuffer(pix, dtype=np.uint8).reshape((h, w, 5))
            pix = arr[..., :4].tobytes()
            mode = 'RGBA'
        elif self.metadata.get('depth') and self.channels == 4 and mode == 'RGB':
             arr = np.frombuffer(pix, dtype=np.uint8).reshape((h, w, 4))
             pix = arr[..., :3].tobytes()
             mode = 'RGB'

        pil_img = Image.frombytes(mode, (w, h), pix)
        return WIMFImage(pil_img, self.metadata)

    async def decode_async(self, **kwargs):
        """Asynchronously decode using a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.decode(**kwargs))

class WIMFEncoder:
    """
    Enterprise-grade WIMF Encoder. 
    Supports deep parameter tuning and seamless app integration.
    """
    def __init__(self, image):
        """
        :param image: PIL.Image, numpy.ndarray, or WIMFImage.
        """
        if isinstance(image, WIMFImage):
            self.pil = image.pil
            self.metadata = image.metadata.copy()
        elif isinstance(image, np.ndarray):
            mode = 'RGB' if image.shape[-1] == 3 else 'RGBA'
            self.pil = Image.fromarray(image, mode)
            self.metadata = {}
        else:
            self.pil = image
            self.metadata = {}
            
        self.tuning = {
            'tile_size': 32,
            'q_matrix': None,
            'lzma_dict_size': None,
            'disable_ycocg': False
        }

    def set_tuning(self, tile_size=32, q_matrix=None, disable_ycocg=False):
        """Deeply tune the codec parameters."""
        self.tuning['tile_size'] = tile_size
        self.tuning['q_matrix'] = q_matrix
        self.tuning['disable_ycocg'] = disable_ycocg
        return self

    def set_metadata(self, **kwargs):
        self.metadata.update(kwargs)
        return self

    def encode(self, quality=7, preset="Balanced", lossless=False):
        """
        Execute encoding pipeline and return the raw WIMF bytes.
        """
        # Prepare pixels
        meta = self.metadata.copy()
        meta['tuning'] = self.tuning # Pass tuning to lower layers
        
        w, h = self.pil.size
        # Simple save logic (wrapping existing saveImage which handles everything)
        # Note: saveImage writes to file, we want bytes. We'll use a temp buffer.
        bio = io.BytesIO()
        # We need to hack saveImage or use encode_lossy directly.
        # Let's use the robust saveImage logic by redirecting output.
        
        # Check for transparency
        has_alpha = self.pil.mode in ('RGBA', 'LA')
        target_mode = 'RGBA' if has_alpha else 'RGB'
        img = self.pil.convert(target_mode)
        pixels = np.array(img)
        
        # 10-bit check
        if meta.get('bit10'):
            pixels = pixels.astype(np.uint16) * 4
            
        # Call the core codec functions
        channels = pixels.shape[-1]
        if lossless:
            data = encode_lossless(pixels.tobytes(), w, h, channels, preset=preset)
            flags = 1
        else:
            data = encode_lossy(pixels.tobytes(), w, h, quality=quality, preset=preset, 
                              channels=channels, bit_depth=(10 if meta.get('bit10') else 8),
                              metadata=meta)
            flags = 10 if (w > 1024 or h > 1024) else 9
            
        m_bytes = json.dumps(meta).encode('utf-8')
        bio.write(b"WIMF")
        bio.write(w.to_bytes(4, 'little') + h.to_bytes(4, 'little'))
        bio.write(flags.to_bytes(1, 'little'))
        bio.write(len(m_bytes).to_bytes(4, 'little') + m_bytes + data)
        
        return bio.getvalue()

    def to_base64(self, **kwargs):
        return base64.b64encode(self.encode(**kwargs)).decode('utf-8')

def open_image(path):
    """Convenience function to open a WIMF file."""
    return WIMFDecoder(path).decode()

def edit_metadata(path):
    """Context manager for surgical metadata editing."""
    class Editor:
        def __init__(self, path): self.path = path
        def __enter__(self):
            self.magic, self.w, self.h, self.flags, self.meta, self.pixels = surgical_read(self.path)
            return self.meta
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                surgical_write(self.path, self.magic, self.w, self.h, self.flags, self.meta, self.pixels)
    return Editor(path)
