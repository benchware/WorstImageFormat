import struct
import numpy as np

# wrap bytes with some parity blocks so if the disk fails we can fix it
def protect(data, num_chunks=10):
    total_len = len(data)
    chunk_size = (total_len + num_chunks - 1) // num_chunks
    
    chunks = []
    for i in range(num_chunks):
        chunk = data[i*chunk_size : (i+1)*chunk_size]
        # pad the end with zeros
        if len(chunk) < chunk_size:
            chunk += b'\x00' * (chunk_size - len(chunk))
        chunks.append(np.frombuffer(chunk, dtype=np.uint8))
        
    # xor all the things. if one breaks, the others can bring it back.
    parity = chunks[0].copy()
    for i in range(1, num_chunks):
        parity ^= chunks[i]
        
    # use 64bit so it doesn't overflow. lost an hour on this bug.
    checksums = [int(np.sum(c, dtype=np.uint64) % 4294967295) for c in chunks]
    
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
        return data, False # not protected, just return it
        
    offset = 4
    orig_len = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    num_chunks = struct.unpack('<I', data[offset:offset+4])[0]; offset += 4
    
    expected_checksums = []
    for _ in range(num_chunks):
        expected_checksums.append(struct.unpack('<I', data[offset:offset+4])[0])
        offset += 4
        
    chunk_size = (orig_len + num_chunks - 1) // num_chunks
    raw_payload = data[offset : offset + orig_len]
    parity_block = np.frombuffer(data[offset + orig_len : offset + orig_len + chunk_size], dtype=np.uint8)
    
    # scan for broken bits
    chunks = []
    broken_idx = -1
    for i in range(num_chunks):
        chunk = raw_payload[i*chunk_size : (i+1)*chunk_size]
        if len(chunk) < chunk_size:
            chunk += b'\x00' * (chunk_size - len(chunk))
        
        c_arr = np.frombuffer(chunk, dtype=np.uint8)
        current_cs = int(np.sum(c_arr, dtype=np.uint64) % 4294967295)
        if current_cs != expected_checksums[i]:
            if broken_idx != -1:
                raise ValueError("too many dead chunks. i cant fix this.")
            broken_idx = i
        chunks.append(c_arr)
        
    if broken_idx == -1:
        return raw_payload, False
        
    print(f"chunk {broken_idx} is dead. fixing it now.")
    
    # math is cool. surviving chunks + parity = missing chunk.
    repaired_chunk = parity_block.copy()
    for i in range(num_chunks):
        if i == broken_idx: continue
        repaired_chunk ^= chunks[i]
        
    repaired_cs = int(np.sum(repaired_chunk, dtype=np.uint64) % 4294967295)
    if repaired_cs != expected_checksums[broken_idx]:
         raise ValueError("repair failed. parity block might be dead too.")
         
    # put it all back together
    new_payload = bytearray()
    for i in range(num_chunks):
        if i == broken_idx:
            target_size = min(chunk_size, orig_len - i*chunk_size)
            new_payload.extend(repaired_chunk[:target_size].tobytes())
        else:
            target_size = min(chunk_size, orig_len - i*chunk_size)
            new_payload.extend(chunks[i][:target_size].tobytes())
            
    print(f"fixed it. bit-rot defeated.")
    return bytes(new_payload), True
