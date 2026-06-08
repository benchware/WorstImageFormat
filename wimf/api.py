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
from . import parity

# basically a wrapper so developers don't have to look at my math
class WIMFImage:
    def __init__(self, pil_image, metadata=None, raw_pixels=None):
        self.pil = pil_image
        self.metadata = metadata or {}
        self.raw_pixels = raw_pixels # keep the full data
        
    @property
    def width(self): return self.pil.width
    
    @property
    def height(self): return self.pil.height
    
    @property
    def size(self): return self.pil.size
    
    @property
    def mode(self): return self.pil.mode
    
    # get the 3d stuff if it's there
    @property
    def depth_map(self):
        if not self.metadata.get('depth') or self.raw_pixels is None: return None
        h, w = self.height, self.width
        channels = self.metadata.get('channels', 3)
        # Depth is the last channel
        arr = np.frombuffer(self.raw_pixels, dtype=np.uint8).reshape((h, w, channels))
        return arr[..., -1]

    def show(self):
        self.pil.show()
        
    def to_numpy(self):
        if self.raw_pixels is not None:
            h, w = self.height, self.width
            chans = self.metadata.get('channels', 3)
            return np.frombuffer(self.raw_pixels, dtype=np.uint8).reshape((h, w, chans))
        return np.array(self.pil)
        
    def to_opencv(self):
        # opencv wants bgr because they are special
        arr = np.array(self.pil.convert('RGB'))
        return arr[:, :, ::-1]

# use this to open files. it's lazy so it's fast.
class WIMFDecoder:
    def __init__(self, source):
        if isinstance(source, (str, bytes, os.PathLike)):
            if isinstance(source, bytes):
                data = source
            else:
                with open(source, 'rb') as f: data = f.read()
        else:
            data = source.read()
            
        # try to fix the file if it's broken
        repaired, was_protected, was_corrupt = parity.verify_and_repair(data)
        self._buffer = io.BytesIO(repaired)
            
        self._parse_header()
        
    @classmethod
    def from_base64(cls, b64_str):
        return cls(base64.b64decode(b64_str))

    # just read the json stuff at the start
    def _parse_header(self):
        self._buffer.seek(0)
        data = self._buffer.read(17) # Read enough for C++ parser
        if len(data) < 17: raise ValueError("file too short")
        
        magic = data[:4]
        if magic not in [b"WIMF", b"AWIF"]:
            raise ValueError("not a wimf file lol")
            
        self.magic = magic
        
        try:
            from . import wimf_cpp
            w, h, flags, mlen = wimf_cpp.parse_header(np.frombuffer(data, dtype=np.uint8))
        except (ImportError, AttributeError):
            w = int.from_bytes(data[4:8], 'little')
            h = int.from_bytes(data[8:12], 'little')
            flags = data[12]
            mlen = int.from_bytes(data[13:17], 'little')
            
        self.width = w
        self.height = h
        self.flags = flags
        
        self._buffer.seek(17)
        self.metadata = json.loads(self._buffer.read(mlen).decode('utf-8'))
        self._data_start = self._buffer.tell()
        
        self.channels = self.metadata.get('channels', 3)
        self.bit_depth = 10 if self.metadata.get('bit10') else 8
        self.is_animated = (magic == b"AWIF")

    # actually do the heavy lifting
    def decode(self, roi=None, target_layer=2, mip_level=0):
        self._buffer.seek(self._data_start)
        data = self._buffer.read()
        
        if self.magic == b"AWIF":
            from .animation import decode_animated
            frames = decode_animated(data, self.width, self.height, self.channels, bit_depth=self.bit_depth)
            pix = frames[0]
        elif self.flags == 1:
            pix = decode_lossless(data, self.width, self.height, self.channels)
        else:
            pix = decode_lossy(data, self.width, self.height, self.channels, 
                              bit_depth=self.bit_depth, target_layer=target_layer, roi=roi, mip_level=mip_level,
                              metadata=self.metadata)
            
        w, h = self.width >> mip_level, self.height >> mip_level
        if roi:
            _, _, w, h = [v >> mip_level for v in roi]
            
        # dumb 10bit to 8bit conversion for pil
        if self.bit_depth == 10:
            arr = np.frombuffer(pix, dtype=np.uint16).reshape((h, w, self.channels))
            pix = (arr >> 2).astype(np.uint8).tobytes()
            
        # standard modes for pil
        if self.channels == 3: mode, pil_pix = 'RGB', pix
        elif self.channels == 4: mode, pil_pix = 'RGBA', pix
        elif self.channels == 5 and self.metadata.get('depth'):
            arr = np.frombuffer(pix, dtype=np.uint8).reshape((h, w, 5))
            pil_pix = arr[..., :4].tobytes()
            mode = 'RGBA'
        else:
            # high channel count fallback: use first 3 channels for a dummy pil image
            try:
                arr = np.frombuffer(pix, dtype=np.uint8).reshape((h, w, self.channels))
                pil_pix = arr[..., :3].tobytes()
                mode = 'RGB'
            except Exception:
                # absolute fallback
                pil_pix = b'\x00' * (w * h * 3)
                mode = 'RGB'

        pil_img = Image.frombytes(mode, (w, h), pil_pix)
        return WIMFImage(pil_img, self.metadata, raw_pixels=pix)

    @property
    def num_states(self):
        if not self.is_animated: return 1
        self._buffer.seek(self._data_start)
        # First 4 bytes after metadata is num_frames
        return int.from_bytes(self._buffer.read(4), 'little')

    # get one state from the undo history
    def decode_chrono_state(self, index=0, **kwargs):
        if not self.is_animated: return self.decode(**kwargs)
        
        if not hasattr(self, '_cached_frames'):
            self._buffer.seek(self._data_start)
            data = self._buffer.read()
            from .animation import decode_animated
            self._cached_frames = decode_animated(data, self.width, self.height, self.channels, bit_depth=self.bit_depth, metadata=self.metadata)
        
        frames = self._cached_frames
        if index >= len(frames): index = len(frames) - 1
        
        pix = frames[index]
        if self.bit_depth == 10:
            arr = np.frombuffer(pix, dtype=np.uint16).reshape((self.height, self.width, self.channels))
            pix = (arr >> 2).astype(np.uint8).tobytes()
            
        # standard modes for pil
        if self.channels == 3: mode, pil_pix = 'RGB', pix
        elif self.channels == 4: mode, pil_pix = 'RGBA', pix
        elif self.channels == 5 and self.metadata.get('depth'):
            arr = np.frombuffer(pix, dtype=np.uint8).reshape((self.height, self.width, 5))
            pil_pix = arr[..., :4].tobytes()
            mode = 'RGBA'
        else:
            # high channel count fallback
            try:
                arr = np.frombuffer(pix, dtype=np.uint8).reshape((self.height, self.width, self.channels))
                pil_pix = arr[..., :3].tobytes()
                mode = 'RGB'
            except Exception:
                pil_pix = b'\x00' * (self.width * self.height * 3)
                mode = 'RGB'

        pil_img = Image.frombytes(mode, (self.width, self.height), pil_pix)
        return WIMFImage(pil_img, self.metadata, raw_pixels=pix)

# use this to build a wimf file
class WIMFEncoder:
    def __init__(self, image):
        if isinstance(image, WIMFImage):
            self.pil = image.pil
            self.metadata = image.metadata.copy()
        elif isinstance(image, np.ndarray):
            h, w = image.shape[:2]
            if h == 0 or w == 0: raise ValueError("image dimensions must be > 0")
            self.raw_data = image
            chans = image.shape[-1]
            
            # Pillow only supports a few modes, so we fallback for N-channel
            try:
                if chans == 5:
                    self.pil = Image.fromarray(image[..., :4], 'RGBA')
                    self.metadata = {'depth': True, 'channels': 5}
                else:
                    mode = 'RGB' if chans == 3 else 'RGBA'
                    self.pil = Image.fromarray(image, mode)
                    self.metadata = {'channels': chans}
            except Exception:
                # Bypassing Pillow for non-standard channel counts
                self.pil = Image.new('RGB', (1, 1))
                self.metadata = {'channels': chans}
        else:
            self.pil = image
            if self.pil.width == 0 or self.pil.height == 0: raise ValueError("image dimensions must be > 0")
            self.metadata = {}
            self.raw_data = None

        self.states = [self.pil] 
        self.metadata = self.metadata or {}
        if 'author' not in self.metadata:
            self.metadata['author'] = "WIMF_User"
        
        self.tuning = {
            'tile_size': 32,
            'q_matrix': None,
            'lzma_dict_size': None,
            'disable_ycocg': False,
            'anti_rot': False
        }

    # anti rot is like data protection but for an image
    def set_anti_rot(self, enabled=True):
        self.tuning['anti_rot'] = enabled
        return self

    def set_tuning(self, tile_size=32, q_matrix=None, disable_ycocg=False, anti_rot=False):
        self.tuning['tile_size'] = tile_size
        self.tuning['q_matrix'] = q_matrix
        self.tuning['disable_ycocg'] = disable_ycocg
        self.tuning['anti_rot'] = anti_rot
        return self

    # add a step to the undo history
    def add_chrono_state(self, image):
        if isinstance(image, np.ndarray):
            if image.size == 0: raise ValueError("empty frame")
            h, w = image.shape[:2]
            if w != self.pil.width or h != self.pil.height:
                raise ValueError(f"frame size mismatch: got {w}x{h}, expected {self.pil.width}x{self.pil.height}")
            mode = 'RGB' if image.shape[-1] == 3 else 'RGBA'
            image = Image.fromarray(image, mode)
        elif isinstance(image, WIMFImage):
            if image.width != self.pil.width or image.height != self.pil.height:
                raise ValueError("image size mismatch")
            image = image.pil
        self.states.append(image)
        return self

    def set_metadata(self, **kwargs):
        self.metadata.update(kwargs)
        return self

    # do the encoding
    def encode(self, quality=7, preset="Balanced", lossless=False):
        meta = self.metadata.copy()
        meta['tuning'] = self.tuning 
        
        # Check for transparency across all states
        has_alpha = any(s.mode in ('RGBA', 'LA') for s in self.states)
        
        if self.raw_data is not None:
            h, w = self.raw_data.shape[:2]
            channels = self.raw_data.shape[2] if len(self.raw_data.shape) > 2 else 1
            if channels >= 4: has_alpha = True
        else:
            w, h = self.pil.size
            channels = len(self.pil.getbands())
            
        target_mode = 'RGBA' if has_alpha else 'RGB'
        meta['channels'] = channels

        pixel_states = []
        actual_channels = 0
        for s in self.states:
            if self.raw_data is not None and len(self.states) == 1:
                pixel_states.append(self.raw_data.tobytes())
                actual_channels = self.raw_data.shape[-1]
            else:
                img = s.convert(target_mode)
                actual_channels = 4 if has_alpha else 3
                if meta.get('bit10'):
                    pixel_states.append((np.array(img).astype(np.uint16) * 4).tobytes())
                else:
                    pixel_states.append(np.array(img).tobytes())

                
        channels = actual_channels
        meta['channels'] = channels
        
        if len(self.states) > 1:
            # use the animation code for undo history
            from .animation import encode_animated
            data = encode_animated(pixel_states, w, h, channels, quality, preset, bit_depth=(10 if meta.get('bit10') else 8))
            magic = b"AWIF"
            flags = 7
        else:
            pixels = pixel_states[0]
            if lossless:
                data = encode_lossless(pixels, w, h, channels, preset=preset)
                flags = 1
            else:
                data = encode_lossy(pixels, w, h, quality=quality, preset=preset, 
                                  channels=channels, bit_depth=(10 if meta.get('bit10') else 8),
                                  metadata=meta)
                flags = 10 if (w > 1024 or h > 1024) else 9
            magic = b"WIMF"
            
        m_bytes = json.dumps(meta).encode('utf-8')
        bio = io.BytesIO()
        bio.write(magic)
        bio.write(w.to_bytes(4, 'little') + h.to_bytes(4, 'little'))
        bio.write(flags.to_bytes(1, 'little'))
        bio.write(len(m_bytes).to_bytes(4, 'little') + m_bytes + data)
        
        final_payload = bio.getvalue()
        if self.tuning.get('anti_rot'):
            print(f"adding anti-rot parity. takes more space but its safe.")
            final_payload = parity.protect(final_payload)
            
        return final_payload

    def to_base64(self, **kwargs):
        return base64.b64encode(self.encode(**kwargs)).decode('utf-8')

def open_image(path):
    return WIMFDecoder(path).decode()

# surgical edit. no re-encoding. nice.
def edit_metadata(path):
    class Editor:
        def __init__(self, path): self.path = path
        def __enter__(self):
            self.magic, self.w, self.h, self.flags, self.meta, self.pixels, self.was_protected = surgical_read(self.path)
            return self.meta
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                surgical_write(self.path, self.magic, self.w, self.h, self.flags, self.meta, self.pixels, protect=self.was_protected)
    return Editor(path)
