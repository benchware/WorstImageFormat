import numpy as np
import lzma
from .core import paeth_predictor, haar_level, ihaar_level

def encode_lossless_channel(channel_2d):
    """Encodes a single 2D channel using Paeth prediction."""
    arr = channel_2d.astype(np.int16)
    res = np.zeros_like(arr)
    res[0, 0] = arr[0, 0]
    res[0, 1:] = arr[0, 1:] - arr[0, :-1]
    res[1:, 0] = arr[1:, 0] - arr[:-1, 0]
    res[1:, 1:] = arr[1:, 1:] - paeth_predictor(arr[1:, :-1], arr[:-1, 1:], arr[:-1, :-1])
    return res.astype(np.uint8).tobytes()

def decode_lossless_channel(data_bytes, w, h):
    """Decodes a single 2D channel using Paeth prediction."""
    res = np.frombuffer(data_bytes, dtype=np.uint8).reshape((h, w)).astype(np.int16)
    arr = np.zeros_like(res)
    arr[0, 0] = res[0, 0]
    for x in range(1, w): arr[0, x] = (res[0, x] + arr[0, x-1]) % 256
    for y in range(1, h): arr[y, 0] = (res[y, 0] + arr[y-1, 0]) % 256
    for y in range(1, h):
        for x in range(1, w):
            a, b, c = arr[y, x-1], arr[y-1, x], arr[y-1, x-1]
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            arr[y, x] = (res[y, x] + pr) % 256
    return arr.astype(np.uint8)

def encode_lossless(pixels, w, h, channels):
    arr = np.frombuffer(pixels, dtype=np.uint8).reshape((h, w, channels)).astype(np.int16)
    res = np.zeros_like(arr)
    res[0, 0] = arr[0, 0]
    res[0, 1:] = arr[0, 1:] - arr[0, :-1]
    res[1:, 0] = arr[1:, 0] - arr[:-1, 0]
    res[1:, 1:] = arr[1:, 1:] - paeth_predictor(arr[1:, :-1], arr[:-1, 1:], arr[:-1, :-1])
    return lzma.compress(res.astype(np.uint8).tobytes(), preset=9)

def decode_lossless(data, w, h, channels):
    res = np.frombuffer(lzma.decompress(data), dtype=np.uint8).reshape((h, w, channels)).astype(np.int16)
    arr = np.zeros_like(res)
    for ch in range(channels):
        arr[0, 0, ch] = res[0, 0, ch]
        for x in range(1, w): arr[0, x, ch] = (res[0, x, ch] + arr[0, x-1, ch]) % 256
        for y in range(1, h): arr[y, 0, ch] = (res[y, 0, ch] + arr[y-1, 0, ch]) % 256
        for y in range(1, h):
            for x in range(1, w):
                a, b, c_val = arr[y, x-1, ch], arr[y-1, x, ch], arr[y-1, x-1, ch]
                p = a + b - c_val
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c_val)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c_val)
                arr[y, x, ch] = (res[y, x, ch] + pr) % 256
    return arr.astype(np.uint8).tobytes()

def encode_lossy(pixels, w, h, quality=5, preset="Balanced", channels=3, bit_depth=8):
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    arr_full = np.frombuffer(pixels, dtype=dtype).reshape((h, w, channels))
    arr = arr_full[..., :3].astype(np.float32) # Only RGB is lossy
    
    mid_point = 2**(bit_depth - 1)
    
    ph, pw = (16 - h % 16) % 16, (16 - w % 16) % 16
    if ph > 0 or pw > 0: arr = np.pad(arr, ((0, ph), (0, pw), (0, 0)), mode='edge')
    
    gh, gw = arr.shape[0] // 16, arr.shape[1] // 16
    blocks = arr.reshape(gh, 16, gw, 16, 3).swapaxes(1, 2)
    
    y = (0.299 * blocks[...,0] + 0.587 * blocks[...,1] + 0.114 * blocks[...,2]) - mid_point
    cb = (mid_point - 0.168736 * blocks[...,0] - 0.331264 * blocks[...,1] + 0.5 * blocks[...,2]) - mid_point
    cr = (mid_point + 0.5 * blocks[...,0] - 0.418688 * blocks[...,1] - 0.081312 * blocks[...,2]) - mid_point
    cb_res, cr_res = cb - (y * 0.1), cr - (y * 0.1)
    
    # Adaptive Quantization
    def process_channel(data, q_base):
        L1_LL, L1_HL, L1_LH, L1_HH = haar_level(data)
        L2_LL, L2_HL, L2_LH, L2_HH = haar_level(L1_LL)
        
        # Scaling quantization steps for high bit depths
        # 10-bit needs smaller steps to preserve that extra precision
        depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))
        
        # Lower noise floor for better detail retention
        noise_floor = max(0.0, (2.0 * depth_scale) - (q_base * 0.2))
        L1_HL[np.abs(L1_HL) < noise_floor] = 0; L1_LH[np.abs(L1_LH) < noise_floor] = 0; L1_HH[np.abs(L1_HH) < noise_floor] = 0
        
        # New, less aggressive quantization formulas
        q_eff = q_base
        q1 = max(1.0, (16.0 * depth_scale) - (q_eff * 1.5))
        q2 = max(1.0, (8.0 * depth_scale) - (q_eff * 0.75))
        
        L2_LL_q = np.round(L2_LL).astype(np.int16)
        L2_HL_q, L2_LH_q, L2_HH_q = np.round(L2_HL/q2).astype(np.int16), np.round(L2_LH/q2).astype(np.int16), np.round(L2_HH/q2).astype(np.int16)
        L1_HL_q, L1_LH_q, L1_HH_q = np.round(L1_HL/q1).astype(np.int16), np.round(L1_LH/q1).astype(np.int16), np.round(L1_HH/q1).astype(np.int16)
        
        return [L2_LL_q, L2_HL_q, L2_LH_q, L2_HH_q, L1_HL_q, L1_LH_q, L1_HH_q]

    y_bands = process_channel(y, quality)
    cb_bands = process_channel(cb_res, quality - 1)
    cr_bands = process_channel(cr_res, quality - 1)
    
    # Dynamic Dictionary Priming (Data Restructuring)
    # Group all base frequencies first, then all mid, then all high.
    payload = bytearray()
    for i in range(7):
        payload.extend(y_bands[i].tobytes())
        payload.extend(cb_bands[i].tobytes())
        payload.extend(cr_bands[i].tobytes())
        
    meta = bytes([quality << 4 | 8]) # Mode 8: Software Perfection
    
    # Lossless-Alpha Hybrid Mode
    if channels == 4:
        alpha_stream = encode_lossless_channel(arr_full[..., 3])
        payload.extend(alpha_stream)
        
    lvl = 9 if preset == "Extreme" else 2
    return lzma.compress(meta + bytes(payload), preset=lvl)

def decode_lossy(data, w, h, channels, bit_depth=8):
    payload = lzma.decompress(data)
    quality = payload[0] >> 4
    gh, gw = (h + 15) // 16, (w + 15) // 16
    bc = gh * gw
    sz_L2, sz_L1 = bc * 16 * 2, bc * 64 * 2
    
    mid_point = 2**(bit_depth - 1)
    depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))

    offset = 1
    bands = [[], [], []] # Y, Cb, Cr
    
    # Entropy-Aware Re-Quantization mapping
    q_base = quality
    
    def get_steps(q):
        q_eff = q
        q1 = max(1.0, (16.0 * depth_scale) - (q_eff * 1.5))
        q2 = max(1.0, (8.0 * depth_scale) - (q_eff * 0.75))
        return q1, q2

    luma_q1, luma_q2 = get_steps(q_base)
    chroma_q1, chroma_q2 = get_steps(max(1, q_base - 1))
    
    for i, sz in enumerate([sz_L2, sz_L2, sz_L2, sz_L2, sz_L1, sz_L1, sz_L1]):
        for c in range(3): # Y, Cb, Cr
            chunk = np.frombuffer(payload[offset : offset+sz], dtype=np.int16).astype(np.float32)
            offset += sz
            
            # De-quantize using channel-specific steps
            q1, q2 = (luma_q1, luma_q2) if c == 0 else (chroma_q1, chroma_q2)
            
            if i > 0 and i < 4: chunk *= q2
            elif i >= 4: chunk *= q1
            
            shape = (gh, gw, 4, 4) if i < 4 else (gh, gw, 8, 8)
            bands[c].append(chunk.reshape(shape))
            
    def reconstruct_channel(b_list):
        L1_LL = ihaar_level(b_list[0], b_list[1], b_list[2], b_list[3])
        return ihaar_level(L1_LL, b_list[4], b_list[5], b_list[6])

    y_rec = reconstruct_channel(bands[0])
    cb_rec = reconstruct_channel(bands[1]) + (y_rec * 0.1)
    cr_rec = reconstruct_channel(bands[2]) + (y_rec * 0.1)
    
    y, cb, cr = y_rec + mid_point, cb_rec + mid_point, cr_rec + mid_point
    cb_f, cr_f = cb - mid_point, cr - mid_point
    
    limit = 2**bit_depth - 1
    r = np.clip(y + 1.402 * cr_f, 0, limit)
    g = np.clip(y - 0.344136 * cb_f - 0.714136 * cr_f, 0, limit)
    b = np.clip(y + 1.772 * cb_f, 0, limit)
    
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    img_rgb = np.stack([r, g, b], axis=-1).astype(dtype)
    img_rgb = img_rgb.swapaxes(1, 2).reshape(gh * 16, gw * 16, 3)[:h, :w]
    
    if channels == 4:
        alpha_data = payload[offset:]
        alpha_channel = decode_lossless_channel(alpha_data, w, h)
        # Note: Alpha is currently always 8-bit in this hybrid mode, 
        # we might need to upscale it if bit_depth > 8
        if bit_depth > 8:
            alpha_channel = (alpha_channel.astype(np.uint16) * (limit // 255)).astype(np.uint16)
        return np.dstack((img_rgb, alpha_channel)).tobytes()
        
    return img_rgb.tobytes()
