import numpy as np
import lzma
import json
import struct

# --- WIMF OPEN-SOURCE ENGINE v18.2 (Animated & Live Photo Update) ---

# --- CORE MATH (ARM-Optimized via NumPy) ---
def paeth_predictor(a, b, c):
    p = a + b - c
    pa, pb, pc = np.abs(p - a), np.abs(p - b), np.abs(p - c)
    return np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))

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
    return arr.astype(np.uint8).tobytes()

def haar_level(b):
    LL = (b[:,:,0::2,0::2] + b[:,:,0::2,1::2] + b[:,:,1::2,0::2] + b[:,:,1::2,1::2]) / 4.0
    HL = (b[:,:,0::2,0::2] - b[:,:,0::2,1::2] + b[:,:,1::2,0::2] - b[:,:,1::2,1::2]) / 4.0
    LH = (b[:,:,0::2,0::2] + b[:,:,0::2,1::2] - b[:,:,1::2,0::2] - b[:,:,1::2,1::2]) / 4.0
    HH = (b[:,:,0::2,0::2] - b[:,:,0::2,1::2] - b[:,:,1::2,0::2] + b[:,:,1::2,1::2]) / 4.0
    return LL, HL, LH, HH

def ihaar_level(LL, HL, LH, HH):
    b = np.zeros((LL.shape[0], LL.shape[1], LL.shape[2]*2, LL.shape[3]*2), dtype=np.float32)
    b[:,:,0::2,0::2], b[:,:,0::2,1::2] = LL + HL + LH + HH, LL - HL + LH - HH
    b[:,:,1::2,0::2], b[:,:,1::2,1::2] = LL + HL - LH - HH, LL - HL - LH + HH
    return b

def encode_lossy(pixels, w, h, quality=5, preset="Balanced", channels=3):
    arr = np.frombuffer(pixels, dtype=np.uint8).reshape((h, w, channels)).astype(np.float32)
    ph, pw = (16 - h % 16) % 16, (16 - w % 16) % 16
    if ph > 0 or pw > 0: arr = np.pad(arr, ((0, ph), (0, pw), (0, 0)), mode='edge')
    
    gh, gw = arr.shape[0] // 16, arr.shape[1] // 16
    blocks = arr.reshape(gh, 16, gw, 16, channels).swapaxes(1, 2)
    
    y = (0.299 * blocks[...,0] + 0.587 * blocks[...,1] + 0.114 * blocks[...,2]) - 128
    cb = (128 - 0.168736 * blocks[...,0] - 0.331264 * blocks[...,1] + 0.5 * blocks[...,2]) - 128
    cr = (128 + 0.5 * blocks[...,0] - 0.418688 * blocks[...,1] - 0.081312 * blocks[...,2]) - 128
    cb_res, cr_res = cb - (y * 0.1), cr - (y * 0.1)
    
    def process_channel(data, q_base):
        L1_LL, L1_HL, L1_LH, L1_HH = haar_level(data)
        L2_LL, L2_HL, L2_LH, L2_HH = haar_level(L1_LL)
        
        noise_floor = max(1.0, 6.0 - (q_base * 0.5))
        L1_HL[np.abs(L1_HL) < noise_floor] = 0; L1_LH[np.abs(L1_LH) < noise_floor] = 0; L1_HH[np.abs(L1_HH) < noise_floor] = 0
        
        q1 = max(1, 30 - (q_base * 3))
        q2 = max(1, 15 - (q_base * 1.5))
        
        L2_LL_q = np.round(L2_LL).astype(np.int16)
        L2_HL_q, L2_LH_q, L2_HH_q = np.round(L2_HL/q2).astype(np.int16), np.round(L2_LH/q2).astype(np.int16), np.round(L2_HH/q2).astype(np.int16)
        L1_HL_q, L1_LH_q, L1_HH_q = np.round(L1_HL/q1).astype(np.int16), np.round(L1_LH/q1).astype(np.int16), np.round(L1_HH/q1).astype(np.int16)
        
        return b"".join([x.tobytes() for x in [L2_LL_q, L2_HL_q, L2_LH_q, L2_HH_q, L1_HL_q, L1_LH_q, L1_HH_q]])

    yb, ym, yf = process_channel(y, quality)[:3]
    meta = bytes([quality << 4 | 5])
    lvl = 9 if preset == "Extreme" else 2
    return lzma.compress(meta + process_channel(y, quality) + process_channel(cb_res, quality-2) + process_channel(cr_res, quality-2), preset=lvl)

def decode_lossy(data, w, h, channels):
    payload = lzma.decompress(data)
    quality = payload[0] >> 4
    gh, gw = (h + 15) // 16, (w + 15) // 16
    bc = gh * gw
    sz_L2, sz_L1 = bc * 16 * 2, bc * 64 * 2
    ch_sz = (sz_L2 * 4) + (sz_L1 * 3)
    
    def reconstruct_channel(start, q_base):
        q1 = max(1, 30 - (q_base * 3))
        q2 = max(1, 15 - (q_base * 1.5))
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
    cb_rec = reconstruct_channel(1 + ch_sz, quality - 2) + (y_rec * 0.1)
    cr_rec = reconstruct_channel(1 + ch_sz * 2, quality - 2) + (y_rec * 0.1)
    
    y, cb, cr = y_rec + 128, cb_rec + 128, cr_rec + 128
    cb_f, cr_f = cb - 128, cr - 128
    r = np.clip(y + 1.402 * cr_f, 0, 255)
    g = np.clip(y - 0.344136 * cb_f - 0.714136 * cr_f, 0, 255)
    b = np.clip(y + 1.772 * cb_f, 0, 255)
    
    img = np.stack([r, g, b], axis=-1).astype(np.uint8)
    return img.swapaxes(1, 2).reshape(gh * 16, gw * 16, 3)[:h, :w, :].tobytes()

# --- AWIF / LWIF (ANIMATION & LIVE PHOTO) ---

def encode_animated(frames, w, h, channels, quality=5, preset="Balanced", is_live_photo=False, audio_bytes=None):
    """
    Encodes multiple frames. 
    Frame 0: I-Frame (Full Lossy Encode)
    Frame N: P-Frame (Inter-frame Delta encoded via LZMA)
    """
    out_payload = bytearray()
    out_payload.extend(struct.pack('<I', len(frames)))
    
    # Opus Audio Payload Structure for Live Photos
    if is_live_photo:
        if audio_bytes:
            # Embed actual Opus/OGG bitstream with OPUS magic identifier
            audio_payload = b'OPUS' + struct.pack('<I', len(audio_bytes)) + audio_bytes
        else:
            # Dummy Opus payload placeholder
            audio_payload = b'OPUS' + struct.pack('<I', 4) + b'\x00\x00\x00\x00'
    else:
        audio_payload = b''
        
    out_payload.extend(struct.pack('<I', len(audio_payload)))
    out_payload.extend(audio_payload)

    prev_arr = None
    for i, frame in enumerate(frames):
        if i == 0:
            # I-Frame (Keyframe)
            compressed = encode_lossy(frame, w, h, quality, preset, channels)
            out_payload.extend(struct.pack('<I', len(compressed)))
            out_payload.extend(compressed)
            prev_arr = np.frombuffer(frame, dtype=np.uint8).astype(np.int16)
        else:
            # P-Frame (Motion Delta)
            curr_arr = np.frombuffer(frame, dtype=np.uint8).astype(np.int16)
            delta = curr_arr - prev_arr
            # Extremely efficient LZMA compression on motion deltas (Lower preset for speed)
            p_level = 6 if preset == "Extreme" else 2
            compressed = lzma.compress(delta.astype(np.int8).tobytes(), preset=p_level)
            out_payload.extend(struct.pack('<I', len(compressed)))
            out_payload.extend(compressed)
            prev_arr = curr_arr

    return bytes(out_payload)

def decode_animated(data, w, h, channels):
    """Returns a list of frame byte arrays."""
    offset = 0
    num_frames = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    audio_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    
    audio_data = data[offset : offset + audio_len]; offset += audio_len
    
    frames = []
    prev_arr = None
    
    for i in range(num_frames):
        frame_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
        frame_data = data[offset : offset + frame_len]; offset += frame_len
        
        if i == 0:
            # I-Frame
            decompressed = decode_lossy(frame_data, w, h, channels)
            frames.append(decompressed)
            prev_arr = np.frombuffer(decompressed, dtype=np.uint8).astype(np.int16)
        else:
            # P-Frame
            delta = np.frombuffer(lzma.decompress(frame_data), dtype=np.int8).astype(np.int16)
            curr_arr = prev_arr + delta
            # Ensure valid byte range after delta addition
            curr_arr = np.clip(curr_arr, 0, 255).astype(np.uint8)
            frames.append(curr_arr.tobytes())
            prev_arr = curr_arr.astype(np.int16)
            
    return frames, audio_data

# --- STANDARD I/O ---

def loadImage(filename):
    with open(filename, 'rb') as f:
        header = f.read(4)
        if header not in [b"WIMF", b"AWIF", b"LWIF"]: 
            raise ValueError(f"Invalid Magic Byte: {header}")
            
        w, h = int.from_bytes(f.read(4), 'little'), int.from_bytes(f.read(4), 'little')
        flags = int.from_bytes(f.read(1), 'little')
        mlen = int.from_bytes(f.read(4), 'little')
        meta = json.loads(f.read(mlen).decode('utf-8')) if mlen > 0 else {}
        data = f.read()
        
        channels = meta.get('channels', 3)
        
        # Determine if we are returning a single frame or a list of frames
        if header in [b"AWIF", b"LWIF"]:
            frames, audio = decode_animated(data, w, h, channels)
            meta['is_animated'] = True
            if header == b"LWIF": meta['is_live_photo'] = True
            return w, h, frames, meta
            
        # Single frame logic
        if flags == 1: pix = decode_lossless(data, w, h, channels)
        elif flags in [5, 6]: pix = decode_lossy(data, w, h, channels)
        else: pix = data
        return w, h, pix, meta

def saveImage(filename, w, h, pixels, compression=1, quality=5, metadata=None, preset="Balanced", audio_bytes=None):
    if metadata is None: metadata = {}
    
    is_animated = isinstance(pixels, list)
    is_live = metadata.get("is_live_photo", False)
    
    channels = len(pixels[0]) // (w * h) if is_animated else len(pixels) // (w * h)
    metadata['channels'] = channels
    
    m_bytes = json.dumps(metadata).encode('utf-8')
    
    # Determine Magic Byte
    magic = b"LWIF" if is_live else (b"AWIF" if is_animated else b"WIMF")
    
    if is_animated or is_live:
        data = encode_animated(pixels if is_animated else [pixels], w, h, channels, quality, preset, is_live, audio_bytes)
        final_flags = 7 # Animated Flag
    else:
        if compression == 2:
            data = encode_lossy(pixels, w, h, quality=quality, preset=preset, channels=channels)
            final_flags = 6
        elif compression == 1:
            data = encode_lossless(pixels, w, h, channels)
            final_flags = 1
        else:
            data = pixels
            final_flags = 0
        
    with open(filename, 'wb') as f:
        f.write(magic)
        f.write(w.to_bytes(4, 'little') + h.to_bytes(4, 'little'))
        f.write(final_flags.to_bytes(1, 'little'))
        f.write(len(m_bytes).to_bytes(4, 'little') + m_bytes + data)

import subprocess
import tempfile
import glob
import os
from PIL import Image

def extract_video_data(video_path, max_duration=5, fps=12, target_w=None, target_h=None):
    """
    Parses an MP4/MOV file using FFMPEG.
    Limits to max_duration (default 5s) for Live Photo efficiency.
    Returns: width, height, list of RGB frame bytes, audio bytes (opus).
    """
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except Exception:
        raise RuntimeError("FFMPEG is required to import video files. Please install FFMPEG and add it to your system PATH.")
        
    temp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(temp_dir, 'audio.opus')
    frames_pattern = os.path.join(temp_dir, 'frame_%04d.bmp')
    
    # Extract audio (convert to opus directly)
    subprocess.run(['ffmpeg', '-y', '-i', video_path, '-t', str(max_duration), '-c:a', 'libopus', '-b:a', '64k', audio_path], 
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Extract frames at a reasonable fps (Live Photos don't need 60fps)
    vf_args = f'fps={fps}'
    if target_w and target_h:
        vf_args += f',scale={target_w}:{target_h}'
        
    subprocess.run(['ffmpeg', '-y', '-i', video_path, '-t', str(max_duration), '-vf', vf_args, frames_pattern], 
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    audio_bytes = b''
    if os.path.exists(audio_path):
        with open(audio_path, 'rb') as f:
            audio_bytes = f.read()
            
    frame_files = sorted(glob.glob(os.path.join(temp_dir, 'frame_*.bmp')))
    if not frame_files:
        raise RuntimeError("Failed to extract frames from video. Check if the file is valid.")
        
    frames = []
    w, h = None, None
    for ff in frame_files:
        img = Image.open(ff).convert('RGB')
        if w is None:
            w, h = img.width, img.height
        frames.append(img.tobytes())
        os.remove(ff)
        
    if os.path.exists(audio_path): os.remove(audio_path)
    os.rmdir(temp_dir)
    
    return w, h, frames, audio_bytes
