import numpy as np

try:
    from . import wimf_cpp
    HAS_CPP = True
except ImportError:
    HAS_CPP = False

def paeth_predictor(a, b, c):
    p = a + b - c
    pa, pb, pc = np.abs(p - a), np.abs(p - b), np.abs(p - c)
    return np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))

def haar_level(b):
    if HAS_CPP:
        return wimf_cpp.haar_level(b.astype(np.float32))
    LL = (b[:,:,0::2,0::2] + b[:,:,0::2,1::2] + b[:,:,1::2,0::2] + b[:,:,1::2,1::2]) / 4.0
    HL = (b[:,:,0::2,0::2] - b[:,:,0::2,1::2] + b[:,:,1::2,0::2] - b[:,:,1::2,1::2]) / 4.0
    LH = (b[:,:,0::2,0::2] + b[:,:,0::2,1::2] - b[:,:,1::2,0::2] - b[:,:,1::2,1::2]) / 4.0
    HH = (b[:,:,0::2,0::2] - b[:,:,0::2,1::2] - b[:,:,1::2,0::2] + b[:,:,1::2,1::2]) / 4.0
    return LL, HL, LH, HH

def ihaar_level(LL, HL, LH, HH):
    if HAS_CPP:
        return wimf_cpp.ihaar_level(LL.astype(np.float32), HL.astype(np.float32), 
                                  LH.astype(np.float32), HH.astype(np.float32))
    b = np.zeros((LL.shape[0], LL.shape[1], LL.shape[2]*2, LL.shape[3]*2), dtype=np.float32)
    b[:,:,0::2,0::2], b[:,:,0::2,1::2] = LL + HL + LH + HH, LL - HL + LH - HH
    b[:,:,1::2,0::2], b[:,:,1::2,1::2] = LL + HL - LH - HH, LL - HL - LH + HH
    return b
