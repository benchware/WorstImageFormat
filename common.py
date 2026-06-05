import numpy as np
import lzma
import json

def haar_level(b):
    LL = (b[:,:,0::2,0::2] + b[:,:,0::2,1::2] + b[:,:,1::2,0::2] + b[:,:,1::2,1::2]) / 4.0
    HL = (b[:,:,0::2,0::2] - b[:,:,0::2,1::2] + b[:,:,1::2,0::2] - b[:,:,1::2,1::2]) / 4.0
    LH = (b[:,:,0::2,0::2] + b[:,:,0::2,1::2] - b[:,:,1::2,0::2] - b[:,:,1::2,1::2]) / 4.0
    HH = (b[:,:,0::2,0::2] - b[:,:,0::2,1::2] - b[:,:,1::2,0::2] + b[:,:,1::2,1::2]) / 4.0
    return LL, HL, LH, HH

def ihaar_level(LL, HL, LH, HH):
    b = np.zeros((LL.shape[0], LL.shape[1], LL.shape[2]*2, LL.shape[3]*2), dtype=np.float32)
    b[:,:,0::2,0::2] = LL + HL + LH + HH
    b[:,:,0::2,1::2] = LL - HL + LH - HH
    b[:,:,1::2,0::2] = LL + HL - LH - HH
    b[:,:,1::2,1::2] = LL - HL - LH + HH
    return b

def ycbcr_to_rgb(y, cb, cr):
    cb_f, cr_f = cb - 128, cr - 128
    r = np.clip(y + 1.402 * cr_f, 0, 255)
    g = np.clip(y - 0.344136 * cb_f - 0.714136 * cr_f, 0, 255)
    b = np.clip(y + 1.772 * cb_f, 0, 255)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)

def encode_lossy(pixels, w, h, quality=5, preset="Balanced"):
    arr = np.frombuffer(pixels, dtype=np.uint8).reshape((h, w, 3)).astype(np.float32)
    ph, pw = (16 - h % 16) % 16, (16 - w % 16) % 16
    if ph > 0 or pw > 0: arr = np.pad(arr, ((0, ph), (0, pw), (0, 0)), mode='edge')
    
    gh, gw = arr.shape[0] // 16, arr.shape[1] // 16
    blocks = arr.reshape(gh, 16, gw, 16, 3).swapaxes(1, 2)
    
    r, g, b_c = blocks[...,0], blocks[...,1], blocks[...,2]
    y = (0.299 * r + 0.587 * g + 0.114 * b_c) - 128
    cb = (128 - 0.168736 * r - 0.331264 * g + 0.5 * b_c) - 128
    cr = (128 + 0.5 * r - 0.418688 * g - 0.081312 * b_c) - 128
    
    cb_res = cb - (y * 0.1)
    cr_res = cr - (y * 0.1)
    
    def process_channel(data, q_base):
        L1_LL, L1_HL, L1_LH, L1_HH = haar_level(data)
        L2_LL, L2_HL, L2_LH, L2_HH = haar_level(L1_LL)
        
        noise_floor = max(1.0, 6.0 - (q_base * 0.5))
        L1_HL[np.abs(L1_HL) < noise_floor] = 0
        L1_LH[np.abs(L1_LH) < noise_floor] = 0
        L1_HH[np.abs(L1_HH) < noise_floor] = 0
        
        q1 = max(1, 45 - (q_base * 4))
        q2 = max(1, 25 - (q_base * 2))
        
        L2_LL_q = np.round(L2_LL).astype(np.int16)
        L2_HL_q, L2_LH_q, L2_HH_q = np.round(L2_HL/q2).astype(np.int16), np.round(L2_LH/q2).astype(np.int16), np.round(L2_HH/q2).astype(np.int16)
        L1_HL_q, L1_LH_q, L1_HH_q = np.round(L1_HL/q1).astype(np.int16), np.round(L1_LH/q1).astype(np.int16), np.round(L1_HH/q1).astype(np.int16)
        
        return b"".join([x.tobytes() for x in [L2_LL_q, L2_HL_q, L2_LH_q, L2_HH_q, L1_HL_q, L1_LH_q, L1_HH_q]])

    y_s = process_channel(y, quality)
    cb_s = process_channel(cb_res, quality - 3)
    cr_s = process_channel(cr_res, quality - 3)
    
    meta = bytes([quality << 4 | 5])
    lvl = 9 if preset == "Extreme" else 2
    return lzma.compress(meta + y_s + cb_s + cr_s, preset=lvl)

def decode_lossy(data, w, h):
    payload = lzma.decompress(data)
    quality = payload[0] >> 4
    gh, gw = (h + 15) // 16, (w + 15) // 16
    bc = gh * gw
    sz_L2, sz_L1 = bc * 16 * 2, bc * 64 * 2
    ch_sz = (sz_L2 * 4) + (sz_L1 * 3)
    
    def reconstruct_channel(start, q_base):
        q1 = max(1, 45 - (q_base * 4))
        q2 = max(1, 25 - (q_base * 2))
        o = start
        L2_LL = np.frombuffer(payload[o:o+sz_L2], dtype=np.int16).reshape((gh, gw, 4, 4)).astype(np.float32); o += sz_L2
        L2_HL = np.frombuffer(payload[o:o+sz_L2], dtype=np.int16).reshape((gh, gw, 4, 4)).astype(np.float32)*q2; o += sz_L2
        L2_LH = np.frombuffer(payload[o:o+sz_L2], dtype=np.int16).reshape((gh, gw, 4, 4)).astype(np.float32)*q2; o += sz_L2
        L2_HH = np.frombuffer(payload[o:o+sz_L2], dtype=np.int16).reshape((gh, gw, 4, 4)).astype(np.float32)*q2; o += sz_L2
        L1_LL = ihaar_level(L2_LL, L2_HL, L2_LH, L2_HH)
        L1_HL = np.frombuffer(payload[o:o+sz_L1], dtype=np.int16).reshape((gh, gw, 8, 8)).astype(np.float32)*q1; o += sz_L1
        L1_LH = np.frombuffer(payload[o:o+sz_L1], dtype=np.int16).reshape((gh, gw, 8, 8)).astype(np.float32)*q1; o += sz_L1
        L1_HH = np.frombuffer(payload[o:o+sz_L1], dtype=np.int16).reshape((gh, gw, 8, 8)).astype(np.float32)*q1; o += sz_L1
        return ihaar_level(L1_LL, L1_HL, L1_LH, L1_HH)

    y_rec = reconstruct_channel(1, quality)
    cb_rec_res = reconstruct_channel(1 + ch_sz, quality - 3)
    cr_rec_res = reconstruct_channel(1 + ch_sz * 2, quality - 3)
    cb_rec, cr_rec = cb_rec_res + (y_rec * 0.1), cr_rec_res + (y_rec * 0.1)
    
    img = ycbcr_to_rgb(y_rec + 128, cb_rec + 128, cr_rec + 128)
    return img.swapaxes(1, 2).reshape(gh * 16, gw * 16, 3)[:h, :w, :].tobytes()

def loadImage(filename):
    with open(filename, 'rb') as f:
        header = f.read(4)
        if header != b"WIMF": raise ValueError("Invalid WIMF")
        w, h = int.from_bytes(f.read(4), 'little'), int.from_bytes(f.read(4), 'little')
        flags = int.from_bytes(f.read(1), 'little')
        mlen = int.from_bytes(f.read(4), 'little')
        meta = json.loads(f.read(mlen).decode('utf-8')) if mlen > 0 else {}
        data = f.read()
        if flags == 1: pix = lzma.decompress(data)
        elif flags in [2, 3, 4, 5]: pix = decode_lossy(data, w, h)
        else: pix = data
        return w, h, pix, meta

def saveImage(filename, w, h, pixels, compression=1, quality=5, metadata=None, preset="Balanced"):
    m_bytes = json.dumps(metadata or {}).encode('utf-8')
    final_flags = 5 if compression == 2 else compression
    if compression == 1: data = lzma.compress(pixels, preset=1)
    elif compression == 2: data = encode_lossy(pixels, w, h, quality=quality, preset=preset)
    else: data = pixels
    with open(filename, 'wb') as f:
        f.write(b"WIMF")
        f.write(w.to_bytes(4, 'little') + h.to_bytes(4, 'little'))
        f.write(final_flags.to_bytes(1, 'little'))
        f.write(len(m_bytes).to_bytes(4, 'little') + m_bytes + data)
