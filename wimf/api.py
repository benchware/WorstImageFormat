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
    
    # get the 3d stuff if it's there
    @property
    def depth_map(self):
        if not self.metadata.get('depth'): return None
        arr = np.array(self.pil)
        return arr[..., -1]

    def show(self):
        self.pil.show()
        
    def to_numpy(self):
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
        repaired, was_corrupt = parity.verify_and_repair(data)
        self._buffer = io.BytesIO(repaired)
            
        self._parse_header()
        
    @classmethod
    def from_base64(cls, b64_str):
        return cls(base64.b64decode(b64_str))

    # just read the json stuff at the start
    def _parse_header(self):
        self._buffer.seek(0)
        magic = self._buffer.read(4)
        if magic not in [b"WIMF", b"AWIF"]:
            raise ValueError("not a wimf file lol")
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
                              bit_depth=self.bit_depth, target_layer=target_layer, roi=roi, mip_level=mip_level)
            
        w, h = self.width >> mip_level, self.height >> mip_level
        if roi:
            _, _, w, h = [v >> mip_level for v in roi]
            
        # dumb 10bit to 8bit conversion for pil
        if self.bit_depth == 10:
            arr = np.frombuffer(pix, dtype=np.uint16).reshape((h, w, self.channels))
            pix = (arr >> 2).astype(np.uint8).tobytes()
            
        mode = 'RGBA' if self.channels >= 4 else 'RGB'
        # strip depth channel if it's there or pil will complain
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

    @property
    def num_states(self):
        if not self.is_animated: return 1
        return 1 # TODO: actually count frames later

    # get one state from the undo history
    def decode_chrono_state(self, index=0, **kwargs):
        if not self.is_animated: return self.decode(**kwargs)
        
        self._buffer.seek(self._data_start)
        data = self._buffer.read()
        from .animation import decode_animated
        frames = decode_animated(data, self.width, self.height, self.channels, bit_depth=self.bit_depth)
        
        if index >= len(frames): index = len(frames) - 1
        
        pix = frames[index]
        if self.bit_depth == 10:
            arr = np.frombuffer(pix, dtype=np.uint16).reshape((self.height, self.width, self.channels))
            pix = (arr >> 2).astype(np.uint8).tobytes()
            
        mode = 'RGBA' if self.channels >= 4 else 'RGB'
        pil_img = Image.frombytes(mode, (self.width, self.height), pix)
        return WIMFImage(pil_img, self.metadata)

# use this to build a wimf file
class WIMFEncoder:
    def __init__(self, image):
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
            mode = 'RGB' if image.shape[-1] == 3 else 'RGBA'
            image = Image.fromarray(image, mode)
        elif isinstance(image, WIMFImage):
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
        
        w, h = self.pil.size
        
        has_alpha = any(s.mode in ('RGBA', 'LA') for s in self.states)
        target_mode = 'RGBA' if has_alpha else 'RGB'
        
        pixel_states = []
        for s in self.states:
            img = s.convert(target_mode)
            if meta.get('bit10'):
                pixel_states.append((np.array(img).astype(np.uint16) * 4).tobytes())
            else:
                pixel_states.append(np.array(img).tobytes())
                
        channels = 4 if has_alpha else 3
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
            self.magic, self.w, self.h, self.flags, self.meta, self.pixels = surgical_read(self.path)
            return self.meta
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                surgical_write(self.path, self.magic, self.w, self.h, self.flags, self.meta, self.pixels)
    return Editor(path)
