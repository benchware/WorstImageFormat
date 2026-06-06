from PIL import Image
from .io import saveImage, loadImage
import sys
import os
import argparse

from PIL import Image, ExifTags, ImageSequence

def convert(input_path, output_path, compression=1, quality=5, preset="Balanced", meta=None):
    try:
        if meta is None: meta = {"author": "Unknown", "engine": "WIMF Open Suite v19.0"}
        in_ext = os.path.splitext(input_path)[1].lower()
        out_ext = os.path.splitext(output_path)[1].lower()

        if in_ext in ['.wimf', '.wif', '.awif']:
            # Decode WIMF to Image
            w, h, pixels, loaded_meta = loadImage(input_path)
            channels = loaded_meta.get('channels', 3)
            img_mode = 'RGBA' if channels >= 4 else 'RGB'

            if out_ext == '.gif':
                if isinstance(pixels, list):
                    # Animated
                    frames = [Image.frombytes(img_mode, (w, h), f) for f in pixels]
                    frames[0].save(output_path, save_all=True, append_images=frames[1:], optimize=False, duration=33, loop=0)
                    print(f"[WIMF] Animation exported to GIF: {output_path}")
                else:
                    # Still
                    img = Image.frombytes(img_mode, (w, h), pixels)
                    img.save(output_path)
                    print(f"[WIMF] Image exported to GIF: {output_path}")
                return

            # If animated, just extract the first frame for standard image conversion
            if isinstance(pixels, list):
                pixels = pixels[0]
                print(f"[WIMF] Note: Extracted first frame of animated sequence.")
                
            img = Image.frombytes(img_mode, (w, h), pixels)
            img.save(output_path)
            print(f"[WIMF] Extraction complete: {output_path}")
            print(f"[WIMF] Metadata - Author: {loaded_meta.get('author', 'Unknown')}")
        
        elif out_ext in ['.wimf', '.wif', '.awif']:
            # Encode Image to WIMF
            img = Image.open(input_path)
            
            # --- AUTO METADATA EXTRACTION (EXIF) ---
            exif = img.getexif()
            if exif:
                for tag, value in exif.items():
                    tag_name = ExifTags.TAGS.get(tag, tag)
                    if isinstance(value, bytes): value = value.decode('utf-8', 'ignore')
                    meta[f"exif_{tag_name}"] = str(value)

            # --- ANIMATION HANDLING (GIF to AWIF) ---
            is_animated = getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1
            if is_animated or meta.get('is_animated'):
                print(f"[WIMF] Animation sequence detected ({getattr(img, 'n_frames', 1)} frames).")
                
                # Check if ANY frame has transparency
                has_alpha = False
                if img.mode in ('RGBA', 'LA'): has_alpha = True
                elif img.mode == 'P' and 'transparency' in img.info: has_alpha = True
                
                target_mode = 'RGBA' if has_alpha else 'RGB'
                channels = 4 if has_alpha else 3
                
                frames = []
                for frame in ImageSequence.Iterator(img):
                    frames.append(frame.convert(target_mode).tobytes())
                
                pixels = frames
                meta['is_animated'] = True
                meta['channels'] = channels
                print(f"[WIMF] Encoding as {target_mode} Animation.")
            else:
                # --- TRANSPARENCY PRESERVATION (STILL) ---
                has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
                if has_alpha:
                    img = img.convert('RGBA')
                    channels = 4
                    print("[WIMF] Alpha channel detected and preserved.")
                else:
                    img = img.convert('RGB')
                    channels = 3
                pixels = img.tobytes()
                meta['channels'] = channels
            
            w, h = img.size
            saveImage(output_path, w, h, pixels, 
                      compression=compression, quality=quality, metadata=meta, preset=preset)
            
            orig_size = os.path.getsize(input_path)
            new_size = os.path.getsize(output_path)
            ratio = new_size / orig_size if orig_size > 0 else 0
            print(f"[WIMF] Encoding finalized: {output_path} (Quality: {quality})")
            print(f"[WIMF] Input: {orig_size:,} B | Output: {new_size:,} B | Ratio: {ratio:.2f}x")
        
        else:
            # Generic format conversion
            Image.open(input_path).save(output_path)
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
    parser.add_argument("--copyright", help="Set copyright metadata")
    parser.add_argument("--desc", help="Set image description")
    parser.add_argument("--make", help="Set camera make")
    parser.add_argument("--model", help="Set camera model")
    parser.add_argument("--cll", help="Set HDR MaxCLL (Content Light Level)")
    parser.add_argument("--fall", help="Set HDR MaxFALL (Frame Average Light Level)")
    
    # Mode overrides
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--lossless", action="store_true", help="Force WIMF Lossless mode")
    group.add_argument("--raw", action="store_true", help="Force WIMF Raw mode")

    # Experimental Flags
    parser.add_argument("--gpu", choices=['auto', 'opengl', 'vulkan'], nargs='?', const='auto', help="Enable Hardware Acceleration (Default: auto if flag set)")
    parser.add_argument("--alpha", action="store_true", help="Enable RGBA Transparency")
    parser.add_argument("--hdr", action="store_true", help="Enable HDR metadata")
    parser.add_argument("--10bit", dest="bit10", action="store_true", help="Enable 10-bit precision")
    parser.add_argument("--animated", action="store_true", help="Process input as multi-frame animation")
    parser.add_argument("--depth", action="store_true", help="Include 3D Depth-Map layer")

    args = parser.parse_args()
    
    # Logic to determine compression mode
    comp_mode = 2 # Default: Lossy
    if args.lossless: comp_mode = 1
    if args.raw: comp_mode = 0

    # Build metadata
    meta = {"author": args.author, "engine": "WIMF Open Suite v19.0"}
    if args.hdr: meta['hdr'] = True
    if args.bit10: meta['bit10'] = True
    if args.alpha: meta['alpha'] = True
    if args.depth: meta['depth'] = True
    if args.animated: meta['is_animated'] = True
    if args.gpu: meta['gpu_mode'] = args.gpu
    
    # New metadata fields
    if args.copyright: meta['copyright'] = args.copyright
    if args.desc: meta['description'] = args.desc
    if args.make: meta['make'] = args.make
    if args.model: meta['model'] = args.model
    if args.cll: meta['max_cll'] = args.cll
    if args.fall: meta['max_fall'] = args.fall
        
    convert(args.input, args.output, compression=comp_mode, quality=args.quality, preset=args.preset, meta=meta)

if __name__ == "__main__":
    main()
