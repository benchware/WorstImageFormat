import struct
import zlib
import logging
import numpy as np

try:
    from . import wimf_cpp
    HAS_CPP = True
except ImportError:
    HAS_CPP = False

logger = logging.getLogger(__name__)


def _checksum(chunk_bytes):
    """Return a robust 32-bit CRC checksum for a bytes-like object."""
    return zlib.crc32(bytes(chunk_bytes)) & 0xFFFFFFFF


# wrap bytes with some parity blocks so if the disk fails we can fix it
def protect(data, num_chunks=10):
    if num_chunks <= 0:
        raise ValueError("num_chunks must be > 0")
    total_len = len(data)
    if total_len == 0:
        return b"ROT!" + struct.pack('<II', 0, num_chunks) + (b'\x00' * (num_chunks * 4))
    chunk_size = (total_len + num_chunks - 1) // num_chunks

    chunks = []
    checksums = []

    for i in range(num_chunks):
        chunk = data[i*chunk_size : (i+1)*chunk_size]
        # pad the end with zeros
        if len(chunk) < chunk_size:
            chunk += b'\x00' * (chunk_size - len(chunk))

        c_arr = np.frombuffer(chunk, dtype=np.uint8).copy()
        checksums.append(_checksum(c_arr))
        chunks.append(c_arr)

    # xor all the things. if one breaks, the others can bring it back.
    parity = chunks[0].copy()
    for i in range(1, num_chunks):
        if HAS_CPP:
            wimf_cpp.block_xor(parity, chunks[i])
        else:
            parity ^= chunks[i]

    # [SIG][LEN][COUNT][CSUMS...][DATA][PARITY]
    header = b"ROT!"
    header += struct.pack('<I', total_len)
    header += struct.pack('<I', num_chunks)
    for cs in checksums:
        header += struct.pack('<I', cs)

    return header + data + parity.tobytes()


# check if the file is rot and fix it if one chunk is dead
def verify_and_repair(data):
    if not data.startswith(b"ROT!"):
        return data, False, False  # not protected, just return it

    offset = 4
    orig_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    num_chunks = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4

    if num_chunks == 0:
        return data[offset:], True, False  # Nothing to repair
    if len(data) < offset + (num_chunks * 4):
        raise ValueError("malformed parity header")

    expected_checksums = []
    for _ in range(num_chunks):
        expected_checksums.append(struct.unpack('<I', data[offset:offset+4])[0])
        offset += 4

    chunk_size = (orig_len + num_chunks - 1) // num_chunks
    raw_payload = data[offset : offset + orig_len]
    parity_block = np.frombuffer(
        data[offset + orig_len : offset + orig_len + chunk_size], dtype=np.uint8
    ).copy()

    # scan for broken bits
    chunks = []
    broken_idx = -1
    for i in range(num_chunks):
        chunk = raw_payload[i*chunk_size : (i+1)*chunk_size]
        if len(chunk) < chunk_size:
            chunk += b'\x00' * (chunk_size - len(chunk))

        c_arr = np.frombuffer(chunk, dtype=np.uint8).copy()
        current_cs = _checksum(c_arr)

        if current_cs != expected_checksums[i]:
            if broken_idx != -1:
                raise ValueError(
                    "too many corrupted chunks — cannot repair (need exactly one bad chunk)"
                )
            broken_idx = i
        chunks.append(c_arr)

    if broken_idx == -1:
        return raw_payload, True, False

    logger.warning("chunk %d is corrupted, attempting repair via parity", broken_idx)

    # math is cool. surviving chunks + parity = missing chunk.
    repaired_chunk = parity_block.copy()
    for i in range(num_chunks):
        if i == broken_idx:
            continue
        if HAS_CPP:
            wimf_cpp.block_xor(repaired_chunk, chunks[i])
        else:
            repaired_chunk ^= chunks[i]

    repaired_cs = _checksum(repaired_chunk)

    if repaired_cs != expected_checksums[broken_idx]:
        raise ValueError("repair failed — parity block itself may be corrupted")

    # put it all back together
    new_payload = bytearray()
    for i in range(num_chunks):
        target_size = min(chunk_size, orig_len - i * chunk_size)
        if i == broken_idx:
            new_payload.extend(repaired_chunk[:target_size].tobytes())
        else:
            new_payload.extend(chunks[i][:target_size].tobytes())

    logger.info("bit-rot repair successful")
    return bytes(new_payload), True, True
