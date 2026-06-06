import sys
import os
import json
import struct
import argparse

def surgical_read(path):
    with open(path, 'rb') as f:
        magic = f.read(4)
        if magic not in [b"WIMF", b"AWIF"]:
            raise ValueError("Not a WIMF/AWIF file")
        w = int.from_bytes(f.read(4), 'little')
        h = int.from_bytes(f.read(4), 'little')
        flags = int.from_bytes(f.read(1), 'little')
        mlen = int.from_bytes(f.read(4), 'little')
        meta_bytes = f.read(mlen)
        pixel_data = f.read()
        
        meta = json.loads(meta_bytes.decode('utf-8'))
        return magic, w, h, flags, meta, pixel_data

def surgical_write(path, magic, w, h, flags, meta, pixel_data):
    m_bytes = json.dumps(meta).encode('utf-8')
    with open(path, 'wb') as f:
        f.write(magic)
        f.write(w.to_bytes(4, 'little') + h.to_bytes(4, 'little'))
        f.write(flags.to_bytes(1, 'little'))
        f.write(len(m_bytes).to_bytes(4, 'little'))
        f.write(m_bytes)
        f.write(pixel_data)

def main():
    parser = argparse.ArgumentParser(description="WIMF Metadata Surgery Tool")
    parser.add_argument("file", help="WIMF file to edit")
    parser.add_argument("--set", nargs=2, action="append", metavar=("KEY", "VALUE"), help="Set a metadata key-value pair")
    parser.add_argument("--clear", action="append", metavar="KEY", help="Remove a metadata key")
    parser.add_argument("--show", action="store_true", help="Print current metadata")
    
    args = parser.parse_args()
    
    try:
        magic, w, h, flags, meta, pixel_data = surgical_read(args.file)
        
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
            surgical_write(args.file, magic, w, h, flags, meta, pixel_data)
            print(f"[WIMF-META] Successfully updated {args.file}")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
