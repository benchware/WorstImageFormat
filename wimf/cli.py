from PIL import Image
from .io import saveImage, loadImage
import sys
import os
import argparse
import glob

from PIL import Image, ExifTags, ImageSequence
import numpy as np
import base64
import io
import time

def convert(input_path, output_path, compression=1, quality=5, preset="Balanced", meta=None, roi=None, depth_map_path=None):
    try:
        if meta is None: meta = {"author": "Unknown", "engine": "WIMF Open Suite v19.0"}
        in_ext = os.path.splitext(input_path)[1].lower()
        out_ext = os.path.splitext(output_path)[1].lower()

        is_10bit = meta.get('bit10', False)

        if in_ext in ['.wimf', '.wif', '.awif']:
            # Decode WIMF to Image
            w, h, pixels, loaded_meta = loadImage(input_path, roi=roi)

            # If ROI was used, adjust w and h
            if roi:
                _, _, rw, rh = roi
                w, h = rw, rh

            channels = loaded_meta.get('channels', 3)
            is_10bit_file = loaded_meta.get('bit10', False)

            # Downsample 16-bit to 8-bit for standard PIL modes if needed
            if is_10bit_file:
                arr = np.frombuffer(pixels, dtype=np.uint16).reshape((h, w, channels))
                pixels = (arr >> 2).astype(np.uint8).tobytes()
                print("[WIMF] Note: Downsampled 10-bit internal data to 8-bit for display.")

            # If Depth map exists, separate it from RGB(A) for viewing
            has_depth = loaded_meta.get('depth', False)

            if has_depth:
                # We typically only save RGB to standard formats
                print(f"[WIMF] Note: Image contains embedded Depth data (Channel {channels-1}).")
                channels -= 1 

            img_mode = 'RGBA' if channels >= 4 else 'RGB'

            
            # --- ICC PROFILE EXTRACTION ---
            icc = None
            if 'icc_profile' in loaded_meta:
                icc = base64.b64decode(loaded_meta['icc_profile'])

            if out_ext == '.gif':
                if isinstance(pixels, list):
                    # Animated
                    frames = [Image.frombytes(img_mode, (w, h), f) for f in pixels]
                    frames[0].save(output_path, save_all=True, append_images=frames[1:], optimize=False, duration=33, loop=0)
                    print(f"[WIMF] Animation exported to GIF: {output_path}")
                else:
                    # Still
                    img = Image.frombytes(img_mode, (w, h), pixels)
                    img.save(output_path, icc_profile=icc)
                    print(f"[WIMF] Image exported to GIF: {output_path}")
                return

            # If animated, just extract the first frame for standard image conversion
            if isinstance(pixels, list):
                pixels = pixels[0]
                print(f"[WIMF] Note: Extracted first frame of animated sequence.")
                
            img = Image.frombytes(img_mode, (w, h), pixels)
            img.save(output_path, icc_profile=icc)
            print(f"[WIMF] Extraction complete: {output_path}")
            print(f"[WIMF] Metadata - Author: {loaded_meta.get('author', 'Unknown')}")
        
        elif out_ext in ['.wimf', '.wif', '.awif']:
            # Encode Image to WIMF
            img = Image.open(input_path)
            
            # --- ICC PROFILE PRESERVATION ---
            icc = img.info.get('icc_profile')
            if icc:
                meta['icc_profile'] = base64.b64encode(icc).decode('utf-8')
                print("[WIMF] ICC Color Profile preserved.")
            
            # --- EMBEDDED THUMBNAIL GENERATION ---
            thumb = img.copy()
            thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
            thumb_io = io.BytesIO()
            thumb.save(thumb_io, format="WEBP", quality=40)
            meta['thumbnail'] = base64.b64encode(thumb_io.getvalue()).decode('utf-8')
            print(f"[WIMF] Embedded thumbnail generated ({len(meta['thumbnail']) // 1024} KB).")

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
                    f_data = frame.convert(target_mode)
                    if is_10bit:
                        # Upsample 8-bit to 16-bit (scaling 0-255 to 0-1023)
                        f_arr = np.array(f_data).astype(np.uint16) * 4
                        frames.append(f_arr.tobytes())
                    else:
                        frames.append(f_data.tobytes())
                
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
                
                if is_10bit:
                    # Upsample 8-bit to 16-bit
                    pixels = np.array(img).astype(np.uint16) * 4
                else:
                    pixels = np.array(img)
                meta['channels'] = channels

            # --- DEPTH MAP PACKING ---
            if depth_map_path:
                d_img = Image.open(depth_map_path).convert('L').resize(img.size, Image.Resampling.LANCZOS)
                d_arr = np.array(d_img)
                if is_10bit: d_arr = d_arr.astype(np.uint16) * 4
                
                # Ensure pixels is a numpy array
                if not isinstance(pixels, np.ndarray):
                    pixels = np.frombuffer(pixels, dtype=np.uint8).reshape((img.size[1], img.size[0], channels))
                
                # Append depth as extra channel
                pixels = np.dstack((pixels, d_arr))
                meta['depth'] = True
                meta['channels'] = pixels.shape[-1]
                print(f"[WIMF] 3D Depth Map packed as channel {meta['channels']-1}.")
            
            w, h = img.size
            # Convert back to bytes if it was an array
            p_bytes = pixels.tobytes() if isinstance(pixels, np.ndarray) else pixels
            
            saveImage(output_path, w, h, p_bytes, 
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
  wimf-convert -i *.jpg -o ./output_dir/
  wimf-convert -i photo.wimf -o photo.jpg
        """
    )
    
    # FFMPEG-style input/output flags
    parser.add_argument("-i", "--input", nargs='+', required=True, help="Path to source asset(s) or wildcard pattern")
    parser.add_argument("-o", "--output", required=True, help="Path to destination asset or directory")
    
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
    parser.add_argument("--alpha", action="store_true", help="Enable RGBA Transparency")
    parser.add_argument("--hdr", action="store_true", help="Enable HDR metadata")
    parser.add_argument("--10bit", dest="bit10", action="store_true", help="Enable 10-bit precision")
    parser.add_argument("--animated", action="store_true", help="Process input as multi-frame animation")
    parser.add_argument("--depth", action="store_true", help="Include 3D Depth-Map layer")
    parser.add_argument("--depth-map", help="Path to grayscale depth map to embed")
    parser.add_argument("--benchmark", action="store_true", help="Compare WIMF against JPEG and WebP")
    parser.add_argument("--roi", nargs=4, type=int, metavar=("X", "Y", "W", "H"), help="Extract a Region of Interest")
    parser.add_argument("--embed-secret", help="Hide a secret string in the image (Steganography)")
    parser.add_argument("--extract-secret", action="store_true", help="Extract hidden secret from the image")

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
    
    # New metadata fields
    if args.copyright: meta['copyright'] = args.copyright
    if args.desc: meta['description'] = args.desc
    if args.make: meta['make'] = args.make
    if args.model: meta['model'] = args.model
    if args.cll: meta['max_cll'] = args.cll
    if args.fall: meta['max_fall'] = args.fall
    
    if args.embed_secret:
        meta['watermark_payload'] = args.embed_secret
        print(f"[WIMF-STEGO] Embedding Secret: '{args.embed_secret}'")

    if args.extract_secret:
        # Trigger watermark extraction
        _, _, _, loaded_meta = loadImage(args.input[0])
        # Note: extraction happens during decode_lossy inside loadImage
        return

    # Expand wildcards if not done by shell
    input_files = []
    for pattern in args.input:
        matched = glob.glob(pattern)
        if matched:
            input_files.extend(matched)
        else:
            input_files.append(pattern)
            
    if args.benchmark:
        if len(input_files) > 1:
            print("[WIMF] ERROR: Benchmark mode only supports a single input file.")
            sys.exit(1)
        in_file = input_files[0]
        
        # Ensure output is a file path even if a directory was provided
        bench_out = args.output
        if os.path.isdir(bench_out):
            bench_out = os.path.join(bench_out, "bench_result.wimf")
        elif not os.path.splitext(bench_out)[1]: # No extension
            if not os.path.exists(bench_out): os.makedirs(bench_out)
            bench_out = os.path.join(bench_out, "bench_result.wimf")

        print(f"\n[WIMF] --- CODEC BENCHMARK: {os.path.basename(in_file)} ---")
        
        # WIMF Benchmark
        s = time.time()
        convert(in_file, bench_out, compression=comp_mode, quality=args.quality, preset=args.preset, meta=meta)
        t_wimf = time.time() - s
        s_wimf = os.path.getsize(bench_out)
        
        # JPEG Benchmark
        img = Image.open(in_file).convert("RGB")
        s = time.time()
        img.save("bench.jpg", format="JPEG", quality=90)
        t_jpg = time.time() - s
        s_jpg = os.path.getsize("bench.jpg")
        
        # WebP Benchmark
        s = time.time()
        img.save("bench.webp", format="WEBP", quality=80)
        t_webp = time.time() - s
        s_webp = os.path.getsize("bench.webp")
        
        print("\n" + "="*60)
        print(f"{'FORMAT':<15} | {'SIZE':<15} | {'ENCODE TIME':<15} | {'RATIO':<10}")
        print("-" * 60)
        print(f"{'WIMF':<15} | {s_wimf:>12,} B | {t_wimf:>14.3f}s | {1.0:>9.2f}x")
        print(f"{'JPEG (Q90)':<15} | {s_jpg:>12,} B | {t_jpg:>14.3f}s | {s_jpg/s_wimf:>9.2f}x")
        print(f"{'WebP (Q80)':<15} | {s_webp:>12,} B | {t_webp:>14.3f}s | {s_webp/s_wimf:>9.2f}x")
        print("="*60 + "\n")
        
        for f in ["bench.jpg", "bench.webp"]:
            if os.path.exists(f): os.remove(f)
        return

    if len(input_files) > 1:
        if not os.path.exists(args.output):
            os.makedirs(args.output)
            print(f"[WIMF] Created output directory: {args.output}")
        elif not os.path.isdir(args.output):
            print(f"[WIMF] ERROR: Multiple inputs provided but output '{args.output}' is not a directory.")
            sys.exit(1)
            
        for in_file in input_files:
            filename = os.path.basename(in_file)
            # Determine output filename (change extension to .wimf if encoding)
            if comp_mode in [1, 2]:
                out_name = os.path.splitext(filename)[0] + ".wimf"
            else:
                out_name = filename # Placeholder for decoding batch
            
            # Simple heuristic for batch decoding
            in_ext = os.path.splitext(in_file)[1].lower()
            if in_ext in ['.wimf', '.wif', '.awif']:
                out_name = os.path.splitext(filename)[0] + ".png" # Default to PNG for batch extraction
                
            out_file = os.path.join(args.output, out_name)
            print(f"[WIMF] Batch Processing: {in_file} -> {out_file}")
            convert(in_file, out_file, compression=comp_mode, quality=args.quality, preset=args.preset, meta=meta, roi=args.roi, depth_map_path=args.depth_map)
    else:
        convert(input_files[0], args.output, compression=comp_mode, quality=args.quality, preset=args.preset, meta=meta, roi=args.roi, depth_map_path=args.depth_map)

if __name__ == "__main__":
    main()
