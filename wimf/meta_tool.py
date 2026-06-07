import sys
import os
import json
import struct
import argparse

from . import parity

def surgical_read(path):
    with open(path, 'rb') as f:
        data = f.read()
        
    # Auto-repair if needed
    repaired, was_protected, was_corrupt = parity.verify_and_repair(data)
    
    magic = repaired[:4]
    if magic not in [b"WIMF", b"AWIF"]:
        raise ValueError("Not a WIMF/AWIF file")
    
    offset = 4
    w = struct.unpack('<I', repaired[offset:offset+4])[0]; offset += 4
    h = struct.unpack('<I', repaired[offset:offset+4])[0]; offset += 4
    flags = repaired[offset]; offset += 1
    mlen = struct.unpack('<I', repaired[offset:offset+4])[0]; offset += 4
    meta_bytes = repaired[offset:offset+mlen]
    pixel_data = repaired[offset+mlen:]
    
    meta = json.loads(meta_bytes.decode('utf-8'))
    return magic, w, h, flags, meta, pixel_data, was_protected

def surgical_write(path, magic, w, h, flags, meta, pixel_data, protect=False):
    m_bytes = json.dumps(meta).encode('utf-8')
    payload = bytearray()
    payload.extend(magic)
    payload.extend(w.to_bytes(4, 'little'))
    payload.extend(h.to_bytes(4, 'little'))
    payload.extend(flags.to_bytes(1, 'little'))
    payload.extend(len(m_bytes).to_bytes(4, 'little'))
    payload.extend(m_bytes)
    payload.extend(pixel_data)
    
    if protect:
        final_data = parity.protect(bytes(payload))
    else:
        final_data = bytes(payload)
        
    with open(path, 'wb') as f:
        f.write(final_data)

def main():
    parser = argparse.ArgumentParser(description="WIMF Metadata Surgery Tool")
    parser.add_argument("file", help="WIMF file to edit")
    parser.add_argument("--set", nargs=2, action="append", metavar=("KEY", "VALUE"), help="Set a metadata key-value pair")
    parser.add_argument("--clear", action="append", metavar="KEY", help="Remove a metadata key")
    parser.add_argument("--show", action="store_true", help="Print current metadata")
    
    args = parser.parse_args()
    
    try:
        magic, w, h, flags, meta, pixel_data, was_protected = surgical_read(args.file)
        
        if args.show:
            print(f"File: {args.file} ({w}x{h})")
            print(json.dumps(meta, indent=2))
            if not args.set and not args.clear:
                return

        modified = False
        if args.set:
            for k, v in args.set:
                meta[k] = v
                modified = True
        
        if args.clear:
            for k in args.clear:
                if k in meta:
                    del meta[k]
                    modified = True
        
        if modified:
            surgical_write(args.file, magic, w, h, flags, meta, pixel_data, protect=was_protected)
            print(f"[WIMF-META] Successfully updated {args.file}")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
