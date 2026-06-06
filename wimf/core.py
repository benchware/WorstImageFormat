import numpy as np

def paeth_predictor(a, b, c):
    p = a + b - c
    pa, pb, pc = np.abs(p - a), np.abs(p - b), np.abs(p - c)
    return np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))

def haar_level(b):
    """
    2D Integer Haar Transform using the Lifting Scheme.
    Ensures bit-exact reconstruction across all bit-depths.
    """
    b = b.astype(np.int32)
    # Horizontal Lifting
    # d = odd - even
    # s = even + (d >> 1)
    d_h = b[:, :, :, 1::2] - b[:, :, :, 0::2]
    s_h = b[:, :, :, 0::2] + (d_h >> 1)
    
    # Vertical Lifting
    # d = odd - even
    # s = even + (d >> 1)
    HL = s_h[:, :, 1::2, :] - s_h[:, :, 0::2, :]
    LL = s_h[:, :, 0::2, :] + (HL >> 1)
    
    HH = d_h[:, :, 1::2, :] - d_h[:, :, 0::2, :]
    LH = d_h[:, :, 0::2, :] + (HH >> 1)
    
    return LL, HL, LH, HH

def ihaar_level(LL, HL, LH, HH):
    """
    Inverse 2D Integer Haar Transform using the Lifting Scheme.
    """
    LL, HL, LH, HH = LL.astype(np.int32), HL.astype(np.int32), LH.astype(np.int32), HH.astype(np.int32)
    
    # Inverse Vertical
    s_h = np.empty((LL.shape[0], LL.shape[1], LL.shape[2]*2, LL.shape[3]), dtype=np.int32)
    s_h[:, :, 0::2, :] = LL - (HL >> 1)
    s_h[:, :, 1::2, :] = s_h[:, :, 0::2, :] + HL
    
    # Inverse Horizontal
    d_h = np.empty((LL.shape[0], LL.shape[1], LL.shape[2]*2, LL.shape[3]), dtype=np.int32)
    d_h[:, :, 0::2, :] = LH - (HH >> 1)
    d_h[:, :, 1::2, :] = d_h[:, :, 0::2, :] + HH
    
    # Final Merge
    b = np.empty((LL.shape[0], LL.shape[1], LL.shape[2]*2, LL.shape[3]*2), dtype=np.int32)
    b[:, :, :, 0::2] = s_h - (d_h >> 1)
    b[:, :, :, 1::2] = b[:, :, :, 0::2] + d_h
    
    return b.astype(np.float32) # Return as float for consistency with existing codec expectations
