import json
import struct

import numpy as np

try:
    from . import wimf_cpp  # type: ignore[attr-defined]

    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def parse_header(data):
    """Parse the WIMF/AWIF binary header from raw bytes.

    Returns (magic, w, h, flags, mlen) where *mlen* is the length of the
    JSON metadata block that immediately follows the 17-byte fixed header.
    Raises ValueError for files that are too short or have an unknown magic.
    """
    if len(data) < 17:
        raise ValueError("file too short to be a valid WIMF file")

    magic = data[:4]
    if magic not in (b"WIMF", b"AWIF"):
        raise ValueError(f"not a WIMF/AWIF file (got magic {magic!r})")

    try:
        w = struct.unpack_from("<I", data, 4)[0]
        h = struct.unpack_from("<I", data, 8)[0]
        flags = data[12]
        mlen = struct.unpack_from("<I", data, 13)[0]
    except struct.error as exc:
        raise ValueError(f"malformed WIMF header: {exc}") from exc

    return magic, w, h, flags, mlen


def parse_header_and_meta(data):
    """Parse the full header + JSON metadata block.

    Returns (magic, w, h, flags, meta_dict, data_start_offset).
    """
    magic, w, h, flags, mlen = parse_header(data)
    meta_bytes = data[17 : 17 + mlen]
    meta = json.loads(meta_bytes.decode("utf-8")) if mlen > 0 else {}
    return magic, w, h, flags, meta, 17 + mlen


def get_quantization_steps(quality, depth_scale=1.0):
    """Return (q1, q2) quantization step sizes for the given quality level.

    q1 is used for the fine (L1) wavelet layer; q2 for the medium (L2) layer.
    Both are clamped to a minimum of 1.0.
    """
    q1 = max(1.0, (16.0 * depth_scale) - (quality * 1.5))
    q2 = max(1.0, (8.0 * depth_scale) - (quality * 0.75))
    return q1, q2


def paeth_predictor(a, b, c):
    p = a + b - c
    pa, pb, pc = np.abs(p - a), np.abs(p - b), np.abs(p - c)
    return np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))


def haar_level(b):
    if HAS_CPP:
        return wimf_cpp.haar_level(b.astype(np.float32))
    LL = (b[:, :, 0::2, 0::2] + b[:, :, 0::2, 1::2] + b[:, :, 1::2, 0::2] + b[:, :, 1::2, 1::2]) / 4.0
    HL = (b[:, :, 0::2, 0::2] - b[:, :, 0::2, 1::2] + b[:, :, 1::2, 0::2] - b[:, :, 1::2, 1::2]) / 4.0
    LH = (b[:, :, 0::2, 0::2] + b[:, :, 0::2, 1::2] - b[:, :, 1::2, 0::2] - b[:, :, 1::2, 1::2]) / 4.0
    HH = (b[:, :, 0::2, 0::2] - b[:, :, 0::2, 1::2] - b[:, :, 1::2, 0::2] + b[:, :, 1::2, 1::2]) / 4.0
    return LL, HL, LH, HH


def ihaar_level(LL, HL, LH, HH):
    if HAS_CPP:
        return wimf_cpp.ihaar_level(
            LL.astype(np.float32), HL.astype(np.float32), LH.astype(np.float32), HH.astype(np.float32)
        )
    b = np.zeros((LL.shape[0], LL.shape[1], LL.shape[2] * 2, LL.shape[3] * 2), dtype=np.float32)
    b[:, :, 0::2, 0::2], b[:, :, 0::2, 1::2] = LL + HL + LH + HH, LL - HL + LH - HH
    b[:, :, 1::2, 0::2], b[:, :, 1::2, 1::2] = LL + HL - LH - HH, LL - HL - LH + HH
    return b
