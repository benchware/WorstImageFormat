import numpy as np
import lzma
import struct
from .codec import encode_lossy, decode_lossy

from .core import haar_level, ihaar_level

def encode_animated(frames, w, h, channels, quality=5, preset="Balanced", bit_depth=8):
    out_payload = bytearray()
    out_payload.extend(struct.pack('<I', len(frames)))
    out_payload.extend(struct.pack('<I', 0)) 

    prev_arr = None
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    
    # Pre-calculate quantization steps for deltas (more aggressive than stills)
    depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))
    q_step = max(1.0, (20.0 * depth_scale) - (quality * 1.5))

    for i, frame in enumerate(frames):
        # Keyframe every 30 frames to reset error accumulation
        is_keyframe = (i % 30 == 0)
        
        if is_keyframe:
            compressed = encode_lossy(frame, w, h, quality, preset, channels, bit_depth=bit_depth)
            # Add a flag to indicate keyframe: Use the audio length field
            out_payload.extend(struct.pack('<I', len(compressed)))
            out_payload.extend(struct.pack('<I', 1)) # 1 = Keyframe
            out_payload.extend(compressed)
            prev_arr = np.frombuffer(frame, dtype=dtype).reshape(h, w, channels).astype(np.float32)
        else:
            curr_arr = np.frombuffer(frame, dtype=dtype).reshape(h, w, channels).astype(np.float32)
            delta = curr_arr - prev_arr
            
            # --- WAVELET RESIDUAL CODING ---
            cur_h, cur_w, _ = delta.shape
            pad_h, pad_w = cur_h % 2, cur_w % 2
            if pad_h > 0 or pad_w > 0:
                d_padded = np.pad(delta, ((0, pad_h), (0, pad_w), (0, 0)), mode='constant')
            else:
                d_padded = delta
            
            d_input = d_padded.transpose(2, 0, 1)[np.newaxis, ...]
            LL, HL, LH, HH = haar_level(d_input)
            
            # Ultra-Aggressive Quantization for Deltas
            q_step_hf = q_step * 3.0
            
            LL_q = np.round(LL / 2.0).astype(np.int16)
            HL_q = np.round(HL / q_step_hf).astype(np.int16)
            LH_q = np.round(LH / q_step_hf).astype(np.int16)
            HH_q = np.round(HH / q_step_hf).astype(np.int16)
            
            # Zero out insignificant movement
            LL_q[np.abs(LL_q) < 2] = 0
            HL_q[np.abs(HL_q) < 1] = 0
            LH_q[np.abs(LH_q) < 1] = 0
            HH_q[np.abs(HH_q) < 1] = 0
            
            d_payload = LL_q.tobytes() + HL_q.tobytes() + LH_q.tobytes() + HH_q.tobytes()
            
            p_level = 6 if preset == "Extreme" else 1 
            compressed = lzma.compress(d_payload, preset=p_level)
            out_payload.extend(struct.pack('<I', len(compressed)))
            out_payload.extend(struct.pack('<I', 0)) # 0 = Delta
            out_payload.extend(compressed)
            
            # Reconstruct for error tracking
            LL_r = LL_q.astype(np.float32) * 2.0
            HL_r = HL_q.astype(np.float32) * q_step_hf
            LH_r = LH_q.astype(np.float32) * q_step_hf
            HH_r = HH_q.astype(np.float32) * q_step_hf
            
            d_rec_padded = ihaar_level(LL_r, HL_r, LH_r, HH_r)[0].transpose(1, 2, 0)
            d_rec = d_rec_padded[:cur_h, :cur_w, :]
            prev_arr = np.clip(prev_arr + d_rec, 0, 2**bit_depth - 1)
            
    return bytes(out_payload)

def decode_animated(data, w, h, channels, bit_depth=8, metadata=None):
    offset = 0
    num_frames = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    audio_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    offset += audio_len
    
    frames = []
    prev_arr = None
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    limit = 2**bit_depth - 1
    
    # Default quality in case first frame isn't a keyframe (shouldn't happen)
    quality = 5
    depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))
    q_step = max(1.0, (20.0 * depth_scale) - (quality * 1.5))
    
    ph, pw = h % 2, w % 2
    th, tw = (h + ph) // 2, (w + pw) // 2
    sz_coeff = th * tw * channels * 2 
    
    for i in range(num_frames):
        frame_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
        is_keyframe = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
        frame_data = data[offset : offset + frame_len]; offset += frame_len
        
        if is_keyframe:
            decompressed = decode_lossy(frame_data, w, h, channels, bit_depth=bit_depth, metadata=metadata)
            frames.append(decompressed)
            prev_arr = np.frombuffer(decompressed, dtype=dtype).reshape(h, w, channels).astype(np.float32)
            
            quality = frame_data[0] >> 4
            depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))
            q_step = max(1.0, (20.0 * depth_scale) - (quality * 1.5))
        else:
            d_raw = lzma.decompress(frame_data)
            o = 0
            q_step_hf = q_step * 3.0
            
            LL = np.frombuffer(d_raw[o:o+sz_coeff], dtype=np.int16).reshape(1, channels, th, tw).astype(np.float32) * 2.0; o += sz_coeff
            HL = np.frombuffer(d_raw[o:o+sz_coeff], dtype=np.int16).reshape(1, channels, th, tw).astype(np.float32) * q_step_hf; o += sz_coeff
            LH = np.frombuffer(d_raw[o:o+sz_coeff], dtype=np.int16).reshape(1, channels, th, tw).astype(np.float32) * q_step_hf; o += sz_coeff
            HH = np.frombuffer(d_raw[o:o+sz_coeff], dtype=np.int16).reshape(1, channels, th, tw).astype(np.float32) * q_step_hf; o += sz_coeff
            
            d_rec = ihaar_level(LL, HL, LH, HH)[0].transpose(1, 2, 0)[:h, :w]
            curr_arr = np.clip(prev_arr + d_rec, 0, limit).astype(dtype)
            frames.append(curr_arr.tobytes())
            prev_arr = curr_arr.astype(np.float32)
            
    return frames
