import numpy as np
import lzma
import struct
from .core import paeth_predictor, haar_level, ihaar_level
from concurrent.futures import ThreadPoolExecutor
from .hwaccel import get_gpu_manager

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
    
    def decode_channel(ch):
        c_res = res[..., ch]
        c_arr = np.zeros((h, w), dtype=np.int16)
        c_arr[0, :] = np.cumsum(c_res[0, :]) % 256
        c_arr[:, 0] = np.cumsum(c_res[:, 0]) % 256
        
        for y in range(1, h):
            res_row = c_res[y]
            arr_row = c_arr[y]
            prev_row = c_arr[y-1]
            for x in range(1, w):
                a = arr_row[x-1]
                b = prev_row[x]
                c_val = prev_row[x-1]
                p = a + b - c_val
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c_val)
                if pa <= pb and pa <= pc: pr = a
                elif pb <= pc: pr = b
                else: pr = c_val
                arr_row[x] = (res_row[x] + pr) % 256
        return c_arr.astype(np.uint8)

    with ThreadPoolExecutor(max_workers=min(channels, 8)) as executor:
        results = list(executor.map(decode_channel, range(channels)))
    
    for ch, c_arr in enumerate(results):
        arr[..., ch] = c_arr
        
    return arr.astype(np.uint8).tobytes()

def encode_lossy(pixels, w, h, quality=5, preset="Balanced", channels=3, bit_depth=8, progressive=True, gpu_mode=None):
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    arr_full = np.frombuffer(pixels, dtype=dtype).reshape((h, w, -1))
    arr = arr_full[..., :3].astype(np.int32)
    
    # --- HARDWARE ACCELERATION CHECK ---
    gpu = get_gpu_manager(gpu_mode or 'off')
    if gpu.enabled:
        gpu_res = gpu.dispatch_ycocg_fwd(arr, w, h)
        if gpu_res is not None:
            y = gpu_res[..., 0]
            co = gpu_res[..., 1]
            cg = gpu_res[..., 2]
        else:
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
            co = r - b
            tmp = b + (co >> 1)
            cg = g - tmp
            y = tmp + (cg >> 1)
    else:
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        co = r - b
        tmp = b + (co >> 1)
        cg = g - tmp
        y = tmp + (cg >> 1)
    
    # Pad to 16x16 blocks
    ph, pw = (16 - h % 16) % 16, (16 - w % 16) % 16
    if ph > 0 or pw > 0:
        y = np.pad(y, ((0, ph), (0, pw)), mode='edge')
        co = np.pad(co, ((0, ph), (0, pw)), mode='edge')
        cg = np.pad(cg, ((0, ph), (0, pw)), mode='edge')
    
    gh, gw = y.shape[0] // 16, y.shape[1] // 16
    
    def to_blocks(chan):
        return chan.reshape(gh, 16, gw, 16).swapaxes(1, 2).astype(np.float32)

    y_blocks, co_blocks, cg_blocks = to_blocks(y), to_blocks(co), to_blocks(cg)
    
    # Adaptive Quantization
    def process_channel(data, q_base):
        L1_LL, L1_HL, L1_LH, L1_HH = haar_level(data)
        L2_LL, L2_HL, L2_LH, L2_HH = haar_level(L1_LL)
        
        depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))
        noise_floor = max(0.0, 2.0 - (q_base * 0.2))
        
        # Quantization formulas
        q_eff = q_base
        q1 = max(1.0, 16.0 - (q_eff * 1.5))
        q2 = max(1.0, 8.0 - (q_eff * 0.75))
        
        # Apply noise floor to high bands
        for b in [L1_HL, L1_LH, L1_HH]: b[np.abs(b) < (noise_floor)] = 0

        # In-place quantization
        L2_LL_q = np.round(L2_LL).astype(np.int16)
        L2_HL_q = np.round(L2_HL / q2).astype(np.int16)
        L2_LH_q = np.round(L2_LH / q2).astype(np.int16)
        L2_HH_q = np.round(L2_HH / q2).astype(np.int16)
        L1_HL_q = np.round(L1_HL / q1).astype(np.int16)
        L1_LH_q = np.round(L1_LH / q1).astype(np.int16)
        L1_HH_q = np.round(L1_HH / q1).astype(np.int16)
        
        return [L2_LL_q, L2_HL_q, L2_LH_q, L2_HH_q, L1_HL_q, L1_LH_q, L1_HH_q]

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(process_channel, y_blocks, quality),
            executor.submit(process_channel, co_blocks, quality - 1),
            executor.submit(process_channel, cg_blocks, quality - 1)
        ]
        results = [f.result() for f in futures]
    
    y_bands, co_bands, cg_bands = results[0], results[1], results[2]
    
    # --- PROGRESSIVE LAYER PACKING ---
    l0_payload = y_bands[0].tobytes() + co_bands[0].tobytes() + cg_bands[0].tobytes()
    l1_payload = bytearray()
    for i in range(1, 4):
        l1_payload.extend(y_bands[i].tobytes())
        l1_payload.extend(co_bands[i].tobytes())
        l1_payload.extend(cg_bands[i].tobytes())
    l2_payload = bytearray()
    for i in range(4, 7):
        l2_payload.extend(y_bands[i].tobytes())
        l2_payload.extend(co_bands[i].tobytes())
        l2_payload.extend(cg_bands[i].tobytes())

    lvl = 9 if preset == "Extreme" else 2
    c0 = lzma.compress(l0_payload, preset=lvl)
    c1 = lzma.compress(l1_payload, preset=lvl)
    c2 = lzma.compress(l2_payload, preset=lvl)
    
    header = bytes([quality << 4 | 9])
    final_payload = bytearray(header)
    for c in [c0, c1, c2]:
        final_payload.extend(struct.pack('<I', len(c)))
        final_payload.extend(c)
        
    if channels == 4 and arr_full.shape[-1] == 4:
        alpha_stream = encode_lossless_channel(arr_full[..., 3])
        final_payload.extend(alpha_stream)
        
    return bytes(final_payload)

def decode_lossy(data, w, h, channels, bit_depth=8, target_layer=2, mode_flag=9, gpu_mode=None):
    gh, gw = (h + 15) // 16, (w + 15) // 16
    bc = gh * gw
    mid_point = 2**(bit_depth - 1)
    depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))
    limit = 2**bit_depth - 1
    bands = [[], [], []]

    if mode_flag == 9:
        quality = data[0] >> 4
        mode = data[0] & 0x0F
        offset = 1
        chunks = []
        for _ in range(3):
            sz = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
            chunks.append(lzma.decompress(data[offset:offset+sz])); offset += sz
            
        sz_L2 = bc * 16 * 2
        l0_raw = chunks[0]
        for c in range(3):
            chunk = np.frombuffer(l0_raw[c*sz_L2 : (c+1)*sz_L2], dtype=np.int16).astype(np.float32)
            bands[c].append(chunk.reshape(gh, gw, 4, 4))
            
        def get_steps(q):
            q1 = max(1.0, 16.0 - (q * 1.5))
            q2 = max(1.0, 8.0 - (q * 0.75))
            return q1, q2

        luma_q1, luma_q2 = get_steps(quality)
        chroma_q1, chroma_q2 = get_steps(max(1, quality - 1))

        if target_layer >= 1:
            l1_raw = chunks[1]; sz_mid = bc * 16 * 2; o = 0
            for i in range(1, 4):
                for c in range(3):
                    chunk = np.frombuffer(l1_raw[o : o+sz_mid], dtype=np.int16).astype(np.float32)
                    chunk *= (luma_q2 if c == 0 else chroma_q2)
                    bands[c].append(chunk.reshape(gh, gw, 4, 4)); o += sz_mid
        else:
            for c in range(3): 
                for _ in range(3): bands[c].append(np.zeros((gh, gw, 4, 4), dtype=np.float32))

        if target_layer >= 2:
            l2_raw = chunks[2]; sz_fine = bc * 64 * 2; o = 0
            for i in range(4, 7):
                for c in range(3):
                    chunk = np.frombuffer(l2_raw[o : o+sz_fine], dtype=np.int16).astype(np.float32)
                    chunk *= (luma_q1 if c == 0 else chroma_q1)
                    bands[c].append(chunk.reshape(gh, gw, 8, 8)); o += sz_fine
        else:
            for c in range(3): 
                for _ in range(3): bands[c].append(np.zeros((gh, gw, 8, 8), dtype=np.float32))
    else:
        payload = lzma.decompress(data); quality = payload[0] >> 4; mode = payload[0] & 0x0F
        def get_steps(q):
            q1 = max(1.0, 16.0 - (q * 1.5))
            q2 = max(1.0, 8.0 - (q * 0.75))
            return q1, q2
        luma_q1, luma_q2 = get_steps(quality); chroma_q1, chroma_q2 = get_steps(max(1, quality - 1))
        sz_L2, sz_L1 = bc * 16 * 2, bc * 64 * 2; offset = 1
        for i, sz in enumerate([sz_L2, sz_L2, sz_L2, sz_L2, sz_L1, sz_L1, sz_L1]):
            for c in range(3):
                chunk = np.frombuffer(payload[offset : offset+sz], dtype=np.int16).astype(np.float32)
                offset += sz
                q1, q2 = (luma_q1, luma_q2) if c == 0 else (chroma_q1, chroma_q2)
                if i > 0 and i < 4: chunk *= q2
                elif i >= 4: chunk *= q1
                bands[c].append(chunk.reshape((gh, gw, 4, 4) if i < 4 else (gh, gw, 8, 8)))

    def reconstruct_channel(b_list):
        L1_LL = ihaar_level(b_list[0], b_list[1], b_list[2], b_list[3])
        return ihaar_level(L1_LL, b_list[4], b_list[5], b_list[6])

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(reconstruct_channel, bands))
    
    # Results are (gh, gw, 16, 16)
    # Reassemble to (gh*16, gw*16)
    def reassemble(chan_blocks):
        return chan_blocks.swapaxes(1, 2).reshape(gh * 16, gw * 16)

    y_rec = reassemble(results[0])
    c1_rec = reassemble(results[1])
    c2_rec = reassemble(results[2])
    
    gpu = get_gpu_manager(gpu_mode or 'off')
    if mode_flag == 9 and gpu.enabled:
        stack = np.stack([y_rec, c1_rec, c2_rec, np.ones_like(y_rec)], axis=-1)
        gpu_res = gpu.dispatch_ycocg_inv(stack, stack.shape[1], stack.shape[0])
        if gpu_res is not None:
            r, g, b = gpu_res[..., 0], gpu_res[..., 1], gpu_res[..., 2]
        else:
            y_rec -= np.floor(c2_rec / 2.0); g = c2_rec + y_rec; y_rec -= np.floor(c1_rec / 2.0); r = y_rec + c1_rec; b = y_rec
    elif mode_flag == 9:
        y_rec -= np.floor(c2_rec / 2.0); g = c2_rec + y_rec; y_rec -= np.floor(c1_rec / 2.0); r = y_rec + c1_rec; b = y_rec
    else:
        y, cb, cr = y_rec + mid_point, c1_rec + mid_point, c2_rec + mid_point
        cb_f, cr_f = cb - mid_point, cr - mid_point
        r, g, b = y + 1.402 * cr_f, y - 0.344136 * cb_f - 0.714136 * cr_f, y + 1.772 * cb_f

    img_rgb = np.stack([np.clip(r, 0, limit), np.clip(g, 0, limit), np.clip(b, 0, limit)], axis=-1)
    dtype_out = np.uint8 if bit_depth == 8 else np.uint16
    img_final = img_rgb.astype(dtype_out)[:h, :w]
    
    if channels == 4:
        alpha_data = data[offset:] if mode_flag == 9 else payload[offset:]
        alpha_channel = decode_lossless_channel(alpha_data, w, h)
        if bit_depth > 8: alpha_channel = (alpha_channel.astype(np.uint16) * (limit // 255)).astype(np.uint16)
        return np.dstack((img_final, alpha_channel)).tobytes()

    return img_final.tobytes()
