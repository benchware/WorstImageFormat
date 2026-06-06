import numpy as np
import lzma
import struct
from .core import paeth_predictor, haar_level, ihaar_level
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

# just some math to compress one channel without losing pixels
def encode_lossless_channel(channel_2d):
    h, w = channel_2d.shape
    arr = channel_2d.astype(np.int16)
    
    # making copies of the array shifted around so we can guess pixels
    above = np.zeros_like(arr)
    above[1:] = arr[:-1]
    
    left = np.zeros_like(arr)
    left[:, 1:] = arr[:, :-1]
    
    above_left = np.zeros_like(arr)
    above_left[1:, 1:] = arr[:-1, :-1]

    # do all the png style math at once because loops are slow af
    res0 = arr.copy()
    res1 = arr - left
    res2 = arr - above
    
    # this paeth thing is confusing but it basically picks the best neighbor
    p = left + above - above_left
    pa, pb, pc = np.abs(p - left), np.abs(p - above), np.abs(p - above_left)
    pr = np.where((pa <= pb) & (pa <= pc), left, 
            np.where(pb <= pc, above, above_left))
    res3 = arr - pr
    
    # figure out which filter sucks the least for each row
    def row_costs(res):
        signed = (res % 256).astype(np.int8).astype(np.int32)
        return np.sum(np.abs(signed), axis=1)

    scores = np.vstack((row_costs(res0), row_costs(res1), row_costs(res2), row_costs(res3)))
    best_filters = np.argmin(scores, axis=0)
    
    res_stack = np.stack((res0, res1, res2, res3))
    best_rows = res_stack[best_filters, np.arange(h), :]
    
    # pack it all together: [type][data][type][data]...
    out_arr = np.zeros((h, w + 1), dtype=np.uint8)
    out_arr[:, 0] = best_filters.astype(np.uint8)
    out_arr[:, 1:] = (best_rows % 256).astype(np.uint8)
    
    return out_arr.tobytes()

# undo the lossless stuff
def decode_lossless_channel(data_bytes, w, h):
    arr = np.zeros((h, w), dtype=np.uint8)
    offset = 0
    
    for y in range(h):
        f_type = data_bytes[offset]
        offset += 1
        row_res = np.frombuffer(data_bytes[offset:offset+w], dtype=np.uint8)
        offset += w
        
        above = arr[y-1] if y > 0 else np.zeros(w, dtype=np.uint8)
        
        if f_type == 0: # literally just raw pixels
            arr[y] = row_res
        elif f_type == 1: # left pixel math
            arr[y] = np.cumsum(row_res, dtype=np.uint8)
        elif f_type == 2: # top pixel math
            arr[y] = (row_res.astype(np.uint16) + above.astype(np.uint16)).astype(np.uint8)
        elif f_type == 3: # paeth is a nightmare to vectorize so we just loop it
            row_res_int = row_res.astype(np.int16)
            above_int = above.astype(np.int16)
            left = 0
            above_left = 0
            row_out = np.zeros(w, dtype=np.uint8)
            for x in range(w):
                a, b, c = left, above_int[x], above_left
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                val = (row_res_int[x] + pr) % 256
                row_out[x] = val
                left = val
                above_left = b
            arr[y] = row_out
                
    return arr

# high level lossless wrapper
def encode_lossless(pixels, w, h, channels, preset="Balanced"):
    arr = np.frombuffer(pixels, dtype=np.uint8).reshape((h, w, channels))
    payload = bytearray()
    for c in range(channels):
        payload.extend(encode_lossless_channel(arr[..., c]))
        
    # use lzma because zip is for boomers
    lvl = 9 if preset == "Extreme" else (1 if preset == "Fast" else 4)
    return lzma.compress(payload, preset=lvl)

def decode_lossless(data, w, h, channels):
    raw = lzma.decompress(data)
    arr = np.zeros((h, w, channels), dtype=np.uint8)
    sz_chan = h * (w + 1)
    for c in range(channels):
        arr[..., c] = decode_lossless_channel(raw[c*sz_chan : (c+1)*sz_chan], w, h)
    return arr.tobytes()

# the main event. lossy compression using magic wavelets.
def encode_lossy(pixels, w, h, quality=5, preset="Balanced", channels=3, bit_depth=8, progressive=True, metadata=None):
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    arr_full = np.frombuffer(pixels, dtype=dtype).reshape((h, w, channels))
    arr = arr_full[..., :3].astype(np.int32)
    
    # separate luma and chroma so we can compress color more
    tuning = metadata.get('tuning', {}) if metadata else {}
    disable_ycocg = tuning.get('disable_ycocg', False)
    
    if not disable_ycocg:
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        co = r - b
        tmp = b + (co >> 1)
        cg = g - tmp
        y = tmp + (cg >> 1)
    else:
        y, co, cg = arr[..., 0], arr[..., 1], arr[..., 2]
        print("[WIMF-TUNING] ycocg off. probably gonna look like crap.")
    
    # pad it to 16x16 because haar likes powers of 2
    ph, pw = (16 - h % 16) % 16, (16 - w % 16) % 16
    y = np.pad(y, ((0, ph), (0, pw)), mode='edge')
    co = np.pad(co, ((0, ph), (0, pw)), mode='edge')
    cg = np.pad(cg, ((0, ph), (0, pw)), mode='edge')
    
    if channels == 4:
        a_chan = arr_full[..., 3].astype(np.float32)
        a_chan = np.pad(a_chan, ((0, ph), (0, pw)), mode='edge')
    
    gh, gw = y.shape[0] // 16, y.shape[1] // 16

    # quantize and haar one tile
    def process_channel_tile(tile_data, q_base, q_matrix_override=None):
        tile_blocks = tile_data.swapaxes(1, 2).astype(np.float32)
        
        depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))
        noise_floor = max(0.0, (2.0 * depth_scale) - (q_base * 0.2))
        q_eff = q_base
        
        if q_matrix_override:
            q1, q2 = q_matrix_override
        else:
            # idk wtf these formulas do but they make the file small
            q1 = max(1.0, (16.0 * depth_scale) - (q_eff * 1.5))
            q2 = max(1.0, (8.0 * depth_scale) - (q_eff * 0.75))

        L1_LL, L1_HL, L1_LH, L1_HH = haar_level(tile_blocks)
        L2_LL, L2_HL, L2_LH, L2_HH = haar_level(L1_LL)
        
        # kill the noise
        for b in [L1_HL, L1_LH, L1_HH]: b[np.abs(b) < noise_floor] = 0

        L2_LL_q = np.round(L2_LL).astype(np.int16)
        L2_HL_q, L2_LH_q, L2_HH_q = np.round(L2_HL/q2).astype(np.int16), np.round(L2_LH/q2).astype(np.int16), np.round(L2_HH/q2).astype(np.int16)
        L1_HL_q, L1_LH_q, L1_HH_q = np.round(L1_HL/q1).astype(np.int16), np.round(L1_LH/q1).astype(np.int16), np.round(L1_HH/q1).astype(np.int16)
        
        return [L2_LL_q, L2_HL_q, L2_LH_q, L2_HH_q, L1_HL_q, L1_LH_q, L1_HH_q]

    # check if we should use the big-boy tiled mode
    tile_size = tuning.get('tile_size', 32)
    q_matrix = tuning.get('q_matrix')
    
    use_mode_10 = (gh > tile_size or gw > tile_size)
    
    if use_mode_10:
        # --- MODE 10: TILED (FOR BIG IMAGES) ---
        print(f"[WIMF-TUNING] tiling at {tile_size*16}px.")
        tile_payloads = []
        for ty in range(0, gh, tile_size):
            for tx in range(0, gw, tile_size):
                t_y = y.reshape(gh, 16, gw, 16)[ty:ty+tile_size, :, tx:tx+tile_size, :]
                t_co = co.reshape(gh, 16, gw, 16)[ty:ty+tile_size, :, tx:tx+tile_size, :]
                t_cg = cg.reshape(gh, 16, gw, 16)[ty:ty+tile_size, :, tx:tx+tile_size, :]
                
                l_qm = (q_matrix[0], q_matrix[1]) if q_matrix else None
                c_qm = (q_matrix[2], q_matrix[3]) if q_matrix else None
                
                y_bands = process_channel_tile(t_y, quality, l_qm)
                co_bands = process_channel_tile(t_co, max(1, quality - 1), c_qm)
                cg_bands = process_channel_tile(t_cg, max(1, quality - 1), c_qm)
                
                # embed secret msg in the pixels. steganography is cool.
                watermark = metadata.get('watermark_payload') if metadata else None
                if watermark and ty == 0 and tx == 0:
                    bits = ''.join(format(ord(c), '08b') for c in watermark) + '00000000'
                    flat = y_bands[0].flatten()
                    for i in range(min(len(bits), len(flat))):
                        flat[i] = (int(flat[i]) & ~1) | int(bits[i])
                    y_bands[0] = flat.reshape(y_bands[0].shape)
                    print(f"hid {len(bits)//8} bytes in the first tile.")

                layers = [bytearray() for _ in range(3)]
                # layer 0 is the blurry version
                layers[0].extend(y_bands[0].tobytes() + co_bands[0].tobytes() + cg_bands[0].tobytes())
                if channels == 4:
                    t_a = a_chan.reshape(gh, 16, gw, 16)[ty:ty+tile_size, :, tx:tx+tile_size, :]
                    a_bands = process_channel_tile(t_a, quality)
                    layers[0].extend(a_bands[0].tobytes())
                
                # layer 1 & 2 add more sharpness
                for i in range(1, 4):
                    layers[1].extend(y_bands[i].tobytes() + co_bands[i].tobytes() + cg_bands[i].tobytes())
                    if channels == 4: layers[1].extend(a_bands[i].tobytes())
                for i in range(4, 7):
                    layers[2].extend(y_bands[i].tobytes() + co_bands[i].tobytes() + cg_bands[i].tobytes())
                    if channels == 4: layers[2].extend(a_bands[i].tobytes())
                
                lvl = 9 if preset == "Extreme" else 2
                compressed = [lzma.compress(l, preset=lvl) for l in layers]
                tile_payloads.append(compressed)
                
        # smash it all into a file with an offset table so we can skip tiles later
        header = bytes([quality << 4 | 10])
        body = bytearray(header)
        body.extend(struct.pack('<I', tile_size))
        body.extend(struct.pack('<I', len(tile_payloads)))
        
        offset_table = bytearray()
        current_offset = len(body) + (len(tile_payloads) * 3 * 4)
        for tp in tile_payloads:
            for layer_data in tp:
                offset_table.extend(struct.pack('<I', current_offset))
                current_offset += len(layer_data)
        
        body.extend(offset_table)
        for tp in tile_payloads:
            for layer_data in tp:
                body.extend(layer_data)
        return bytes(body)

    if not use_mode_10:
        # --- MODE 9: THE SIMPLE WAY ---
        l_qm = (q_matrix[0], q_matrix[1]) if q_matrix else None
        c_qm = (q_matrix[2], q_matrix[3]) if q_matrix else None

        y_bands = process_channel_tile(y.reshape(gh, 16, gw, 16), quality, l_qm)
        co_bands = process_channel_tile(co.reshape(gh, 16, gw, 16), max(1, quality - 1), c_qm)
        cg_bands = process_channel_tile(cg.reshape(gh, 16, gw, 16), max(1, quality - 1), c_qm)
        if channels == 4: 
            a_bands = process_channel_tile(a_chan.reshape(gh, 16, gw, 16), quality, l_qm)
        
        # embed stego in standard mode too
        watermark = metadata.get('watermark_payload') if metadata else None
        if watermark:
            bits = ''.join(format(ord(c), '08b') for c in watermark) + '00000000'
            flat = y_bands[0].flatten()
            for i in range(min(len(bits), len(flat))):
                flat[i] = (int(flat[i]) & ~1) | int(bits[i])
            y_bands[0] = flat.reshape(y_bands[0].shape)
            print(f"hid {len(bits)//8} bytes in L0.")

        l0_payload = y_bands[0].tobytes() + co_bands[0].tobytes() + cg_bands[0].tobytes()
        if channels == 4: l0_payload += a_bands[0].tobytes()
        l1_payload, l2_payload = bytearray(), bytearray()
        for i in range(1, 4):
            l1_payload.extend(y_bands[i].tobytes() + co_bands[i].tobytes() + cg_bands[i].tobytes())
            if channels == 4: l1_payload.extend(a_bands[i].tobytes())
        for i in range(4, 7):
            l2_payload.extend(y_bands[i].tobytes() + co_bands[i].tobytes() + cg_bands[i].tobytes())
            if channels == 4: l2_payload.extend(a_bands[i].tobytes())

        lvl = 9 if preset == "Extreme" else 2
        with ThreadPoolExecutor(max_workers=3) as executor:
            c0, c1, c2 = [f.result() for f in [executor.submit(lzma.compress, p, preset=lvl) for p in [l0_payload, l1_payload, l2_payload]]]
        
        header = bytes([quality << 4 | 9])
        body = bytearray(header)
        for c in [c0, c1, c2]:
            body.extend(struct.pack('<I', len(c)))
            body.extend(c)
        return bytes(body)

# undo the wavelet magic
def reconstruct_channel(b_list, mip_level=0):
    if mip_level >= 2: return b_list[0] # quarter size (super fast)
    L1_LL = ihaar_level(b_list[0], b_list[1], b_list[2], b_list[3])
    if mip_level == 1: return L1_LL # half size
    return ihaar_level(L1_LL, b_list[4], b_list[5], b_list[6])

# the decoder monster
def decode_lossy(data, w, h, channels, bit_depth=8, target_layer=2, mode_flag=9, roi=None, mip_level=0):
    gh, gw = (h + 15) // 16, (w + 15) // 16
    bc = gh * gw
    
    mid_point = 2**(bit_depth - 1)
    depth_scale = 1.0 if bit_depth == 8 else (2**(bit_depth-8))
    limit = 2**bit_depth - 1

    quality = data[0] >> 4
    mode = data[0] & 0x0F

    if mode == 10:
        # --- TILED DECODING (ROI SUPPORT) ---
        offset = 1
        tile_size = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
        num_tiles = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
        
        cols = (gw + tile_size - 1) // tile_size
        rows = (gh + tile_size - 1) // tile_size
        
        table_sz = num_tiles * 3 * 4
        offset_table_raw = data[offset : offset + table_sz]
        offset_table = struct.unpack('<' + 'I'*(num_tiles*3), offset_table_raw)
        
        # calculate which tiles to actually decode if the user asked for a crop
        if roi:
            rx, ry, rw, rh = roi
            bg_x1, bg_y1 = rx // 16, ry // 16
            bg_x2, bg_y2 = (rx + rw + 15) // 16, (ry + rh + 15) // 16
            tile_x1, tile_y1 = bg_x1 // tile_size, bg_y1 // tile_size
            tile_x2, tile_y2 = (bg_x2 + tile_size - 1) // tile_size, (bg_y2 + tile_size - 1) // tile_size
        else:
            tile_x1, tile_y1, tile_x2, tile_y2 = 0, 0, cols, rows

        block_size = 16 >> mip_level
        full_bands = [np.zeros((gh, gw, block_size, block_size), dtype=np.float32) for _ in range(channels)]
        
        # skip layers if we are doing mipmapping
        eff_target = min(target_layer, 2 - mip_level)

        def decode_tile(tx, ty):
            idx = (ty * cols + tx) * 3
            tile_bands = [[] for _ in range(channels)]
            
            # L0
            l0_off = offset_table[idx]
            l0_end = offset_table[idx+1]
            l0_raw = lzma.decompress(data[l0_off : l0_end])
            
            t_gh = min(tile_size, gh - ty * tile_size)
            t_gw = min(tile_size, gw - tx * tile_size)
            sz_L2 = t_gh * t_gw * 16
            
            for c in range(channels):
                chunk = np.frombuffer(l0_raw[c*sz_L2*2 : (c+1)*sz_L2*2], dtype=np.int16).astype(np.float32)
                tile_bands[c].append(chunk.reshape(t_gh, t_gw, 4, 4))
                
            # try to find a secret msg
            if tx == 0 and ty == 0:
                y_dc = tile_bands[0][0].flatten().astype(np.int16)
                bits = "".join(str(int(val) & 1) for val in y_dc)
                chars = []
                for i in range(0, len(bits), 8):
                    byte = bits[i:i+8]
                    if len(byte) < 8 or byte == '00000000': break
                    chars.append(chr(int(byte, 2)))
                extracted = "".join(chars)
                if extracted:
                    print(f"found a secret: '{extracted}'")
                
            def get_steps(q):
                q1 = max(1.0, (16.0 * depth_scale) - (q * 1.5))
                q2 = max(1.0, (8.0 * depth_scale) - (q * 0.75))
                return q1, q2

            luma_q1, luma_q2 = get_steps(quality)
            chroma_q1, chroma_q2 = get_steps(max(1, quality - 1))

            if eff_target >= 1:
                l1_off = offset_table[idx+1]
                l1_end = offset_table[idx+2]
                l1_raw = lzma.decompress(data[l1_off : l1_end])
                sz_mid = t_gh * t_gw * 16
                o = 0
                for i in range(1, 4):
                    for c in range(channels):
                        chunk = np.frombuffer(l1_raw[o*2 : (o+sz_mid)*2], dtype=np.int16).astype(np.float32)
                        q = luma_q2 if c in [0, 3] else chroma_q2
                        chunk *= q
                        tile_bands[c].append(chunk.reshape(t_gh, t_gw, 4, 4))
                        o += sz_mid
            else:
                for c in range(channels): [tile_bands[c].append(np.zeros((t_gh, t_gw, 4, 4), dtype=np.float32)) for _ in range(3)]

            if eff_target >= 2:
                l2_off = offset_table[idx+2]
                l2_end = offset_table[idx+3] if idx+3 < len(offset_table) else len(data)
                l2_raw = lzma.decompress(data[l2_off : l2_end])
                sz_fine = t_gh * t_gw * 64
                o = 0
                for i in range(4, 7):
                    for c in range(channels):
                        chunk = np.frombuffer(l2_raw[o*2 : (o+sz_fine)*2], dtype=np.int16).astype(np.float32)
                        q = luma_q1 if c in [0, 3] else chroma_q1
                        chunk *= q
                        tile_bands[c].append(chunk.reshape(t_gh, t_gw, 8, 8))
                        o += sz_fine
            else:
                for c in range(channels): [tile_bands[c].append(np.zeros((t_gh, t_gw, 8, 8), dtype=np.float32)) for _ in range(3)]
                
            for c in range(channels):
                t_rec = reconstruct_channel(tile_bands[c], mip_level)
                full_bands[c][ty*tile_size:(ty+1)*tile_size, tx*tile_size:(tx+1)*tile_size] = t_rec
        
        # run it in parallel because my cpu has cores
        with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
            futures = [executor.submit(decode_tile, tx, ty) for ty in range(tile_y1, tile_y2) for tx in range(tile_x1, tile_x2)]
            [f.result() for f in futures]
            
        y_rec, c1_rec, c2_rec = full_bands[:3]
        if channels == 4: a_rec = full_bands[3]
        
        # inverse ycocg math. it works, trust me.
        tmp = y_rec - np.floor(c2_rec / 2.0)
        g = c2_rec + tmp
        b = tmp - np.floor(c1_rec / 2.0)
        r = b + c1_rec
        
        img_rgb = np.stack([np.clip(r, 0, limit), np.clip(g, 0, limit), np.clip(b, 0, limit)], axis=-1)
        dtype = np.uint8 if bit_depth == 8 else np.uint16
        
        img_rgb = img_rgb.astype(dtype).swapaxes(1, 2).reshape(gh * block_size, gw * block_size, 3)
        
        if roi:
            rx, ry, rw, rh = [v >> mip_level for v in roi]
            img_rgb = img_rgb[ry:ry+rh, rx:rx+rw]
        else:
            img_rgb = img_rgb[:h >> mip_level, :w >> mip_level]
            
        if channels == 4:
            alpha_channel = np.clip(a_rec, 0, limit).astype(dtype).swapaxes(1, 2).reshape(gh * block_size, gw * block_size)
            if roi: alpha_channel = alpha_channel[ry:ry+rh, rx:rx+rw]
            else: alpha_channel = alpha_channel[:h >> mip_level, :w >> mip_level]
            return np.dstack((img_rgb, alpha_channel)).tobytes()
        return img_rgb.tobytes()

    elif mode == 9:
        # --- THE OLD WAY ---
        offset = 1
        bands = [[] for _ in range(channels)]
        
        compressed_chunks = []
        for _ in range(3):
            sz = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
            compressed_chunks.append(data[offset:offset+sz]); offset += sz
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            chunks = list(executor.map(lzma.decompress, compressed_chunks))
            
        l0_raw = chunks[0]
        sz_L2 = bc * 16 * 2
        for c in range(channels):
            chunk = np.frombuffer(l0_raw[c*sz_L2 : (c+1)*sz_L2], dtype=np.int16).astype(np.float32)
            bands[c].append(chunk.reshape(gh, gw, 4, 4))
            
        # extract secret msg
        y_dc = bands[0][0].flatten().astype(np.int16)
        bits = "".join(str(int(val) & 1) for val in y_dc)
        chars = []
        for i in range(0, len(bits), 8):
            byte = bits[i:i+8]
            if len(byte) < 8 or byte == '00000000': break
            chars.append(chr(int(byte, 2)))
        extracted = "".join(chars)
        if extracted:
            print(f"found a secret: '{extracted}'")
            
        def get_steps(q):
            q1 = max(1.0, (16.0 * depth_scale) - (q * 1.5))
            q2 = max(1.0, (8.0 * depth_scale) - (q * 0.75))
            return q1, q2

        luma_q1, luma_q2 = get_steps(quality)
        chroma_q1, chroma_q2 = get_steps(max(1, quality - 1))

        if target_layer >= 1:
            l1_raw = chunks[1]
            sz_mid = bc * 16 * 2
            o = 0
            for i in range(1, 4):
                for c in range(channels):
                    chunk = np.frombuffer(l1_raw[o : o+sz_mid], dtype=np.int16).astype(np.float32)
                    q = luma_q2 if c in [0, 3] else chroma_q2 # Alpha (3) uses luma steps
                    chunk *= q
                    bands[c].append(chunk.reshape(gh, gw, 4, 4))
                    o += sz_mid
        else:
            for c in range(channels): 
                for _ in range(3): bands[c].append(np.zeros((gh, gw, 4, 4), dtype=np.float32))

        if target_layer >= 2:
            l2_raw = chunks[2]
            sz_fine = bc * 64 * 2
            o = 0
            for i in range(4, 7):
                for c in range(channels):
                    chunk = np.frombuffer(l2_raw[o : o+sz_fine], dtype=np.int16).astype(np.float32)
                    q = luma_q1 if c in [0, 3] else chroma_q1
                    chunk *= q
                    bands[c].append(chunk.reshape(gh, gw, 8, 8))
                    o += sz_fine
        else:
            for c in range(channels): 
                for _ in range(3): bands[c].append(np.zeros((gh, gw, 8, 8), dtype=np.float32))

    # finish up the reconstruction
    with ThreadPoolExecutor(max_workers=channels) as executor:
        futures = [executor.submit(reconstruct_channel, bands[c], mip_level) for c in range(channels)]
        results = [f.result() for f in futures]
        y_rec, c1_rec, c2_rec = results[:3]
        if channels == 4: a_rec = results[3]
    
    if mode_flag == 9:
        tmp = y_rec - np.floor(c2_rec / 2.0)
        g = c2_rec + tmp
        b = tmp - np.floor(c1_rec / 2.0)
        r = b + c1_rec
    else:
        # legacy ycbcr. idk if anyone still uses this.
        y_rec += (c1_rec * 0.1) 
        y_rec += (c2_rec * 0.1) 
        y, cb, cr = y_rec + mid_point, c1_rec + mid_point, c2_rec + mid_point
        cb_f, cr_f = cb - mid_point, cr - mid_point
        r = y + 1.402 * cr_f
        g = y - 0.344136 * cb_f - 0.714136 * cr_f
        b = y + 1.772 * cb_f

    img_rgb = np.stack([np.clip(r, 0, limit), np.clip(g, 0, limit), np.clip(b, 0, limit)], axis=-1)
    dtype = np.uint8 if bit_depth == 8 else np.uint16
    
    block_size = 16 >> mip_level
    img_rgb = img_rgb.astype(dtype).swapaxes(1, 2).reshape(gh * block_size, gw * block_size, 3)[:h >> mip_level, :w >> mip_level]

    if channels == 4:
        # alpha reassembly. axes are a mess here.
        alpha_channel = np.clip(a_rec, 0, limit).astype(dtype).swapaxes(1, 2).reshape(gh * block_size, gw * block_size)[:h >> mip_level, :w >> mip_level]
        return np.dstack((img_rgb, alpha_channel)).tobytes()

    return img_rgb.tobytes()
