"""Backward-compatible extension chunks appended to a WIM2 image."""

import struct
import zlib

TRAILER = struct.Struct("<4sHHQII")
DIRECTORY_HEADER = struct.Struct("<4sI")
DIRECTORY_ENTRY = struct.Struct("<4sQQII")
TRAILER_MAGIC = b"XEND"
DIRECTORY_MAGIC = b"XDIR"
HISTORY_MAGIC = b"HST2"
PARITY_MAGIC = b"AR2!"
MAX_EXTENSIONS = 64
MAX_HISTORY_STATES = 4096
MAX_EXTENSION_BYTES = 1 << 30


def _crc(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def parse_extensions(data, verify_checksums=True):
    if len(data) < TRAILER.size:
        return {}
    magic, version, _, directory_offset, directory_size, directory_crc = TRAILER.unpack_from(
        data, len(data) - TRAILER.size
    )
    if magic != TRAILER_MAGIC:
        return {}
    if version != 1 or directory_size > MAX_EXTENSION_BYTES:
        raise ValueError("unsupported WIM2 extension trailer")
    trailer_offset = len(data) - TRAILER.size
    if directory_offset > trailer_offset or directory_size > trailer_offset - directory_offset:
        raise ValueError("WIM2 extension directory points outside file")
    raw = data[directory_offset : directory_offset + directory_size]
    if _crc(raw) != directory_crc or len(raw) < DIRECTORY_HEADER.size:
        raise ValueError("WIM2 extension directory checksum mismatch")
    directory_magic, count = DIRECTORY_HEADER.unpack_from(raw)
    if directory_magic != DIRECTORY_MAGIC or count > MAX_EXTENSIONS:
        raise ValueError("invalid WIM2 extension directory")
    if len(raw) != DIRECTORY_HEADER.size + count * DIRECTORY_ENTRY.size:
        raise ValueError("invalid WIM2 extension directory size")
    result = {}
    for index in range(count):
        kind, offset, size, crc, flags = DIRECTORY_ENTRY.unpack_from(
            raw, DIRECTORY_HEADER.size + index * DIRECTORY_ENTRY.size
        )
        if size > MAX_EXTENSION_BYTES or offset > directory_offset or size > directory_offset - offset:
            raise ValueError("WIM2 extension chunk points outside file")
        payload = data[offset : offset + size]
        checksum_valid = _crc(payload) == crc
        if not checksum_valid and verify_checksums:
            if kind != b"AROT":
                raise ValueError(f"WIM2 {kind.decode('ascii', 'replace')} extension checksum mismatch")
        if kind in result:
            raise ValueError("duplicate WIM2 extension type")
        result[kind] = {
            "payload": payload,
            "offset": offset,
            "size": size,
            "flags": flags,
            "checksum_valid": checksum_valid,
        }
    return result


def append_extensions(base, chunks):
    payload = bytearray(base)
    entries = []
    for kind, chunk, flags in chunks:
        if not isinstance(kind, bytes) or len(kind) != 4:
            raise ValueError("extension type must be four bytes")
        if len(chunk) > MAX_EXTENSION_BYTES:
            raise ValueError("WIM2 extension is too large")
        offset = len(payload)
        payload.extend(chunk)
        entries.append(DIRECTORY_ENTRY.pack(kind, offset, len(chunk), _crc(chunk), flags))
    directory_offset = len(payload)
    directory = DIRECTORY_HEADER.pack(DIRECTORY_MAGIC, len(entries)) + b"".join(entries)
    payload.extend(directory)
    payload.extend(TRAILER.pack(TRAILER_MAGIC, 1, 0, directory_offset, len(directory), _crc(directory)))
    return bytes(payload)


def encode_history(states):
    if not 1 <= len(states) <= MAX_HISTORY_STATES:
        raise ValueError("invalid WIM2 history state count")
    out = bytearray(HISTORY_MAGIC + struct.pack("<I", len(states)))
    for state in states:
        if not state.startswith(b"WIM2") or len(state) > MAX_EXTENSION_BYTES:
            raise ValueError("history state is not a bounded WIM2 image")
        out.extend(struct.pack("<QI", len(state), _crc(state)))
        out.extend(state)
    return bytes(out)


def decode_history(payload):
    if len(payload) < 8 or payload[:4] != HISTORY_MAGIC:
        raise ValueError("invalid WIM2 history extension")
    count = struct.unpack_from("<I", payload, 4)[0]
    if not 1 <= count <= MAX_HISTORY_STATES:
        raise ValueError("invalid WIM2 history state count")
    states = []
    position = 8
    for _ in range(count):
        if position + 12 > len(payload):
            raise ValueError("truncated WIM2 history index")
        size, crc = struct.unpack_from("<QI", payload, position)
        position += 12
        if size > MAX_EXTENSION_BYTES or size > len(payload) - position:
            raise ValueError("truncated WIM2 history state")
        state = payload[position : position + size]
        position += size
        if not state.startswith(b"WIM2") or _crc(state) != crc:
            raise ValueError("WIM2 history state checksum mismatch")
        states.append(state)
    if position != len(payload):
        raise ValueError("trailing WIM2 history data")
    return states


def _gf_mul(a, b):
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = ((a << 1) ^ (0x11D if a & 0x80 else 0)) & 0xFF
        b >>= 1
    return result


def _gf_pow(a, power):
    result = 1
    while power:
        if power & 1:
            result = _gf_mul(result, a)
        a = _gf_mul(a, a)
        power >>= 1
    return result


def _gf_div(a, b):
    if not b:
        raise ValueError("invalid anti-rot parity geometry")
    return _gf_mul(a, _gf_pow(b, 254))


def encode_anti_rot(protected, shard_count=10):
    if not protected or not 2 <= shard_count <= 255:
        raise ValueError("invalid anti-rot input")
    shard_size = (len(protected) + shard_count - 1) // shard_count
    shards = []
    checksums = []
    for index in range(shard_count):
        shard = protected[index * shard_size : (index + 1) * shard_size].ljust(shard_size, b"\0")
        shards.append(shard)
        checksums.append(_crc(shard))
    parity_p = bytearray(shard_size)
    parity_q = bytearray(shard_size)
    for index, shard in enumerate(shards):
        coefficient = _gf_pow(2, index)
        for position, value in enumerate(shard):
            parity_p[position] ^= value
            parity_q[position] ^= _gf_mul(value, coefficient)
    header = struct.pack("<4sQII", PARITY_MAGIC, len(protected), shard_count, shard_size)
    return header + struct.pack(f"<{shard_count}I", *checksums) + bytes(parity_p) + bytes(parity_q)


def repair_anti_rot(data, payload):
    if len(payload) < 20 or payload[:4] != PARITY_MAGIC:
        raise ValueError("invalid WIM2 anti-rot extension")
    original_size, shard_count, shard_size = struct.unpack_from("<QII", payload, 4)
    if not 2 <= shard_count <= 255 or not shard_size or original_size > len(data):
        raise ValueError("invalid WIM2 anti-rot geometry")
    header_size = 20 + shard_count * 4
    if len(payload) != header_size + shard_size * 2:
        raise ValueError("invalid WIM2 anti-rot size")
    checksums = struct.unpack_from(f"<{shard_count}I", payload, 20)
    parity_p = payload[header_size : header_size + shard_size]
    parity_q = payload[header_size + shard_size :]
    shards = []
    broken = []
    protected = data[:original_size]
    for index in range(shard_count):
        shard = protected[index * shard_size : (index + 1) * shard_size].ljust(shard_size, b"\0")
        shards.append(bytearray(shard))
        if _crc(shard) != checksums[index]:
            broken.append(index)
    if not broken:
        return data, False
    if len(broken) > 2:
        raise ValueError("too many corrupted WIM2 anti-rot shards")
    syndrome_p = bytearray(parity_p)
    syndrome_q = bytearray(parity_q)
    for index, shard in enumerate(shards):
        if index in broken:
            continue
        coefficient = _gf_pow(2, index)
        for position, value in enumerate(shard):
            syndrome_p[position] ^= value
            syndrome_q[position] ^= _gf_mul(value, coefficient)
    if len(broken) == 1:
        shards[broken[0]] = syndrome_p
    else:
        first, second = broken
        a, b = _gf_pow(2, first), _gf_pow(2, second)
        recovered_first = bytearray(shard_size)
        recovered_second = bytearray(shard_size)
        for position in range(shard_size):
            first_value = _gf_div(syndrome_q[position] ^ _gf_mul(b, syndrome_p[position]), a ^ b)
            recovered_first[position] = first_value
            recovered_second[position] = syndrome_p[position] ^ first_value
        shards[first], shards[second] = recovered_first, recovered_second
    for index in broken:
        if _crc(shards[index]) != checksums[index]:
            raise ValueError("WIM2 anti-rot repair checksum mismatch")
    repaired = b"".join(shards)[:original_size] + data[original_size:]
    return repaired, True


def repair_extensions(data):
    extensions = parse_extensions(data, verify_checksums=False)
    anti_rot = extensions.get(b"AROT")
    if anti_rot is None:
        return data, False, False
    repaired, changed = repair_anti_rot(data, anti_rot["payload"])
    if not anti_rot["checksum_valid"] and not changed:
        raise ValueError("WIM2 anti-rot extension checksum mismatch")
    return repaired, True, changed
