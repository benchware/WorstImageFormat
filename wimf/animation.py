import numpy as np
import lzma
import struct
from .codec import encode_lossy, decode_lossy

def encode_animated(frames, w, h, channels, quality=5, preset="Balanced", bit_depth=8):
    out_payload = bytearray()
    out_payload.extend(struct.pack('<I', len(frames)))
    out_payload.extend(struct.pack('<I', 0)) # 0 audio payload length for compatibility

    prev_arr = None
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    
    for i, frame in enumerate(frames):
        if i == 0:
            compressed = encode_lossy(frame, w, h, quality, preset, channels, bit_depth=bit_depth)
            out_payload.extend(struct.pack('<I', len(compressed)))
            out_payload.extend(compressed)
            prev_arr = np.frombuffer(frame, dtype=dtype).astype(np.int32)
        else:
            curr_arr = np.frombuffer(frame, dtype=dtype).astype(np.int32)
            delta = curr_arr - prev_arr
            p_level = 6 if preset == "Extreme" else 2
            # Use int16 for deltas to handle range [-1023, 1023] or [-255, 255]
            compressed = lzma.compress(delta.astype(np.int16).tobytes(), preset=p_level)
            out_payload.extend(struct.pack('<I', len(compressed)))
            out_payload.extend(compressed)
            prev_arr = curr_arr
    return bytes(out_payload)

def decode_animated(data, w, h, channels, bit_depth=8):
    offset = 0
    num_frames = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    audio_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    offset += audio_len
    
    frames = []
    prev_arr = None
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    limit = 2**bit_depth - 1
    
    for i in range(num_frames):
        frame_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
        frame_data = data[offset : offset + frame_len]; offset += frame_len
        
        if i == 0:
            decompressed = decode_lossy(frame_data, w, h, channels, bit_depth=bit_depth)
            frames.append(decompressed)
            prev_arr = np.frombuffer(decompressed, dtype=dtype).astype(np.int32)
        else:
            delta = np.frombuffer(lzma.decompress(frame_data), dtype=np.int16).astype(np.int32)
            curr_arr = np.clip(prev_arr + delta, 0, limit).astype(dtype)
            frames.append(curr_arr.tobytes())
            prev_arr = curr_arr.astype(np.int32)
            
    return frames
