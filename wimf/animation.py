import numpy as np
import lzma
import struct
from .codec import encode_lossy, decode_lossy

def encode_animated(frames, w, h, channels, quality=5, preset="Balanced"):
    out_payload = bytearray()
    out_payload.extend(struct.pack('<I', len(frames)))
    out_payload.extend(struct.pack('<I', 0)) # 0 audio payload length for compatibility

    prev_arr = None
    for i, frame in enumerate(frames):
        if i == 0:
            compressed = encode_lossy(frame, w, h, quality, preset, channels)
            out_payload.extend(struct.pack('<I', len(compressed)))
            out_payload.extend(compressed)
            prev_arr = np.frombuffer(frame, dtype=np.uint8).astype(np.int16)
        else:
            curr_arr = np.frombuffer(frame, dtype=np.uint8).astype(np.int16)
            delta = curr_arr - prev_arr
            p_level = 6 if preset == "Extreme" else 2
            compressed = lzma.compress(delta.astype(np.int8).tobytes(), preset=p_level)
            out_payload.extend(struct.pack('<I', len(compressed)))
            out_payload.extend(compressed)
            prev_arr = curr_arr
    return bytes(out_payload)

def decode_animated(data, w, h, channels):
    offset = 0
    num_frames = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    audio_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    offset += audio_len
    
    frames = []
    prev_arr = None
    
    for i in range(num_frames):
        frame_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
        frame_data = data[offset : offset + frame_len]; offset += frame_len
        
        if i == 0:
            decompressed = decode_lossy(frame_data, w, h, channels)
            frames.append(decompressed)
            prev_arr = np.frombuffer(decompressed, dtype=np.uint8).astype(np.int16)
        else:
            delta = np.frombuffer(lzma.decompress(frame_data), dtype=np.int8).astype(np.int16)
            curr_arr = np.clip(prev_arr + delta, 0, 255).astype(np.uint8)
            frames.append(curr_arr.tobytes())
            prev_arr = curr_arr.astype(np.int16)
            
    return frames
