from PIL import Image
from .io import saveImage, loadImage
import sys
import os
import argparse

def convert(input_path, output_path, compression=1, quality=5, author="Unknown", preset="Balanced"):
    try:
        in_ext = os.path.splitext(input_path)[1].lower()
        out_ext = os.path.splitext(output_path)[1].lower()
        meta = {"author": author, "engine": "WIMF Open Suite v18.3"}

        if in_ext in ['.wimf', '.wif', '.awif']:
            # Decode WIMF to Image
            w, h, pixels, loaded_meta = loadImage(input_path)
            
            # If animated, just extract the first frame for standard image conversion
            if isinstance(pixels, list):
                pixels = pixels[0]
                print(f"[WIMF] Note: Extracted first frame of animated sequence.")
                
            channels = loaded_meta.get('channels', 3)
            img_mode = 'RGBA' if channels == 4 else 'RGB'
            
            img = Image.frombytes(img_mode, (w, h), pixels)
            img.save(output_path)
            print(f"[WIMF] Extraction complete: {output_path}")
            print(f"[WIMF] Metadata - Author: {loaded_meta.get('author', 'Unknown')}")
        
        elif out_ext in ['.wimf', '.wif', '.awif']:
            # Encode Image to WIMF
            img = Image.open(input_path).convert('RGB')
            w, h = img.size
            pixels = img.tobytes()
            
            saveImage(output_path, w, h, pixels, 
                      compression=compression, quality=quality, metadata=meta, preset=preset)
            
            orig_size = os.path.getsize(input_path)
            new_size = os.path.getsize(output_path)
            ratio = new_size / orig_size if orig_size > 0 else 0
            print(f"[WIMF] Encoding finalized: {output_path} (Quality: {quality})")
            print(f"[WIMF] Input: {orig_size:,} B | Output: {new_size:,} B | Ratio: {ratio:.2f}x")
        
        else:
            # Generic format conversion
            Image.open(input_path).convert('RGB').save(output_path)
            print(f"[WIMF] Format migration successful: {output_path}")

    except Exception as e:
        print(f"[WIMF] CRITICAL ERROR: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="WIMF (Worst IMage Format) Open Suite CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  wimf-convert -i input.png -o output.wimf -q 8 -p Extreme
  wimf-convert -i photo.wimf -o photo.jpg
  wimf-convert -i raw.ppm -o compressed.wimf --lossless
        """
    )
    
    # FFMPEG-style input/output flags
    parser.add_argument("-i", "--input", required=True, help="Path to source asset")
    parser.add_argument("-o", "--output", required=True, help="Path to destination asset")
    
    # Parameter flags
    parser.add_argument("-q", "--quality", type=int, default=7, choices=range(1, 11), help="Quality level (1-10, default: 7)")
    parser.add_argument("-p", "--preset", choices=["Fast", "Balanced", "Extreme"], default="Balanced", help="Engine effort preset")
    parser.add_argument("-a", "--author", default="WIMF_User", help="Set author metadata tag")
    
    # Mode overrides
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--lossless", action="store_true", help="Force WIMF Lossless mode")
    group.add_argument("--raw", action="store_true", help="Force WIMF Raw mode")

    # Experimental Flags
    parser.add_argument("--alpha", action="store_true", help="Enable RGBA Transparency")
    parser.add_argument("--hdr", action="store_true", help="Enable 10-bit HDR precision")
    parser.add_argument("--animated", action="store_true", help="Process input as multi-frame animation")
    parser.add_argument("--depth", action="store_true", help="Include 3D Depth-Map layer")

    args = parser.parse_args()
    
    # Logic to determine compression mode
    comp_mode = 2 # Default: Lossy
    if args.lossless: comp_mode = 1
    if args.raw: comp_mode = 0
        
    convert(args.input, args.output, compression=comp_mode, quality=args.quality, author=args.author, preset=args.preset)

if __name__ == "__main__":
    main()
