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

# some generic converter function. handles basically everything.
def convert(input_path, output_path, compression=1, quality=5, preset="Balanced", meta=None, roi=None, depth_map_path=None, mip_level=0):
    try:
        if meta is None: meta = {"author": "Unknown", "engine": "WIMF Open Suite v19.0"}
        in_ext = os.path.splitext(input_path)[1].lower()
        out_ext = os.path.splitext(output_path)[1].lower()

        is_10bit = meta.get('bit10', False)

        if in_ext in ['.wimf', '.wif', '.awif']:
            # open wimf and turn it back to pixels
            w, h, pixels, loaded_meta = loadImage(input_path, roi=roi, mip_level=mip_level)

            w, h = w >> mip_level, h >> mip_level
            if roi:
                _, _, rw, rh = [v >> mip_level for v in roi]
                w, h = rw, rh
            channels = loaded_meta.get('channels', 3)
            is_10bit_file = loaded_meta.get('bit10', False)

            # downsample 10bit to 8bit because pil is old
            if is_10bit_file:
                arr = np.frombuffer(pixels, dtype=np.uint16).reshape((h, w, channels))
                pixels = (arr >> 2).astype(np.uint8).tobytes()
                print("made it 8-bit so pil doesn't crash.")

            # handle the depth channel. i think it's at the end.
            has_depth = loaded_meta.get('depth', False)

            if has_depth:
                print(f"found depth map at channel {channels-1}. skipping it for now.")
                channels -= 1 

            img_mode = 'RGBA' if channels >= 4 else 'RGB'

            # get the color profile if the photographer is fancy
            icc = None
            if 'icc_profile' in loaded_meta:
                icc = base64.b64decode(loaded_meta['icc_profile'])

            # special case for gifs. everyone loves gifs.
            if out_ext == '.gif':
                if isinstance(pixels, list):
                    frames = [Image.frombytes(img_mode, (w, h), f) for f in pixels]
                    frames[0].save(output_path, save_all=True, append_images=frames[1:], optimize=False, duration=33, loop=0)
                else:
                    img = Image.frombytes(img_mode, (w, h), pixels)
                    img.save(output_path, icc_profile=icc)
                return

            if isinstance(pixels, list):
                pixels = pixels[0]
                print("only extracted frame 0 of the animation.")
                
            img = Image.frombytes(img_mode, (w, h), pixels)
            img.save(output_path, icc_profile=icc)
            print(f"saved to {output_path}. cya.")
        
        elif out_ext in ['.wimf', '.wif', '.awif']:
            # encode whatever into wimf
            img = Image.open(input_path)
            
            # keep the color profile
            icc = img.info.get('icc_profile')
            if icc:
                meta['icc_profile'] = base64.b64encode(icc).decode('utf-8')
            
            # make a tiny preview and hide it in the header. sneaky.
            thumb = img.copy()
            thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
            thumb_io = io.BytesIO()
            thumb.save(thumb_io, format="WEBP", quality=40)
            meta['thumbnail'] = base64.b64encode(thumb_io.getvalue()).decode('utf-8')

            # copy exif tags. i think i got most of them.
            exif = img.getexif()
            if exif:
                for tag, value in exif.items():
                    tag_name = ExifTags.TAGS.get(tag, tag)
                    if isinstance(value, bytes): value = value.decode('utf-8', 'ignore')
                    meta[f"exif_{tag_name}"] = str(value)

            # check if it's a gif. delta encoding is hard.
            is_animated = getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1
            if is_animated or meta.get('is_animated'):
                print("found some frames. encoding as animation.")
                
                has_alpha = False
                if img.mode in ('RGBA', 'LA'): has_alpha = True
                elif img.mode == 'P' and 'transparency' in img.info: has_alpha = True
                
                target_mode = 'RGBA' if has_alpha else 'RGB'
                channels = 4 if has_alpha else 3
                
                frames = []
                for frame in ImageSequence.Iterator(img):
                    f_data = frame.convert(target_mode)
                    if is_10bit:
                        f_arr = np.array(f_data).astype(np.uint16) * 4
                        frames.append(f_arr.tobytes())
                    else:
                        frames.append(f_data.tobytes())
                
                pixels = frames
                meta['is_animated'] = True
                meta['channels'] = channels
            else:
                # normal still image
                has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
                if has_alpha:
                    img = img.convert('RGBA')
                    channels = 4
                else:
                    img = img.convert('RGB')
                    channels = 3
                
                if is_10bit:
                    pixels = np.array(img).astype(np.uint16) * 4
                else:
                    pixels = np.array(img)
                meta['channels'] = channels

            # hide a depth map if the user gave us one
            if depth_map_path:
                d_img = Image.open(depth_map_path).convert('L').resize(img.size, Image.Resampling.LANCZOS)
                d_arr = np.array(d_img)
                if is_10bit: d_arr = d_arr.astype(np.uint16) * 4
                
                if not isinstance(pixels, np.ndarray):
                    pixels = np.frombuffer(pixels, dtype=np.uint8).reshape((img.size[1], img.size[0], channels))
                
                pixels = np.dstack((pixels, d_arr))
                meta['depth'] = True
                meta['channels'] = pixels.shape[-1]
            
            w, h = img.size
            p_bytes = pixels.tobytes() if isinstance(pixels, np.ndarray) else pixels
            
            saveImage(output_path, w, h, p_bytes, 
                      compression=compression, quality=quality, metadata=meta, preset=preset)
            
            orig_size = os.path.getsize(input_path)
            new_size = os.path.getsize(output_path)
            ratio = new_size / orig_size if orig_size > 0 else 0
            print(f"done. file is {new_size} bytes now.")
        
        else:
            # i don't know what this extension is but pil might
            Image.open(input_path).save(output_path)

    except Exception as e:
        print(f"bruh: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="WIMF CLI Tool")
    
    parser.add_argument("-i", "--input", nargs='+', required=True, help="source file")
    parser.add_argument("-o", "--output", required=True, help="dest file or folder")
    
    parser.add_argument("-q", "--quality", type=int, default=7, choices=range(1, 11))
    parser.add_argument("-p", "--preset", choices=["Fast", "Balanced", "Extreme"], default="Balanced")
    parser.add_argument("-a", "--author", default="WIMF_User")
    parser.add_argument("--copyright")
    parser.add_argument("--desc")
    parser.add_argument("--make")
    parser.add_argument("--model")
    parser.add_argument("--cll")
    parser.add_argument("--fall")
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--lossless", action="store_true")
    group.add_argument("--raw", action="store_true")

    parser.add_argument("--alpha", action="store_true")
    parser.add_argument("--hdr", action="store_true")
    parser.add_argument("--10bit", dest="bit10", action="store_true")
    parser.add_argument("--animated", action="store_true")
    parser.add_argument("--depth", action="store_true")
    parser.add_argument("--depth-map")
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--roi", nargs=4, type=int)
    parser.add_argument("--mip", type=int, default=0, choices=[0, 1, 2])
    parser.add_argument("--anti-rot", action="store_true")
    parser.add_argument("--chrono", action="store_true")
    parser.add_argument("--extract-chrono", type=int)
    parser.add_argument("--embed-secret")
    parser.add_argument("--extract-secret", action="store_true")

    args = parser.parse_args()
    
    comp_mode = 2 
    if args.lossless: comp_mode = 1
    if args.raw: comp_mode = 0

    meta = {"author": args.author, "engine": "WIMF Open Suite v19.0"}
    if args.hdr: meta['hdr'] = True
    if args.bit10: meta['bit10'] = True
    if args.alpha: meta['alpha'] = True
    if args.depth: meta['depth'] = True
    if args.animated: meta['is_animated'] = True
    if args.anti_rot: meta['tuning'] = {'anti_rot': True}
    
    if args.copyright: meta['copyright'] = args.copyright
    if args.desc: meta['description'] = args.desc
    if args.make: meta['make'] = args.make
    if args.model: meta['model'] = args.model
    if args.cll: meta['max_cll'] = args.cll
    if args.fall: meta['max_fall'] = args.fall
    
    if args.embed_secret:
        meta['watermark_payload'] = args.embed_secret

    if args.extract_secret:
        _, _, _, loaded_meta = loadImage(args.input[0])
        return

    # wildcards are a pain
    input_files = []
    for pattern in args.input:
        matched = glob.glob(pattern)
        if matched: input_files.extend(matched)
        else: input_files.append(pattern)
            
    if args.benchmark:
        if len(input_files) > 1:
            sys.exit(1)
        in_file = input_files[0]
        
        bench_out = args.output
        if os.path.isdir(bench_out):
            bench_out = os.path.join(bench_out, "bench_result.wimf")
        elif not os.path.splitext(bench_out)[1]: 
            if not os.path.exists(bench_out): os.makedirs(bench_out)
            bench_out = os.path.join(bench_out, "bench_result.wimf")

        print(f"benchmarking {in_file}...")
        
        s = time.time()
        convert(in_file, bench_out, compression=comp_mode, quality=args.quality, preset=args.preset, meta=meta)
        t_wimf = time.time() - s
        s_wimf = os.path.getsize(bench_out)
        
        img = Image.open(in_file).convert("RGB")
        s = time.time()
        img.save("bench.jpg", format="JPEG", quality=90)
        t_jpg = time.time() - s
        s_jpg = os.path.getsize("bench.jpg")
        
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
        elif not os.path.isdir(args.output):
            sys.exit(1)
            
        for in_file in input_files:
            filename = os.path.basename(in_file)
            if comp_mode in [1, 2]: out_name = os.path.splitext(filename)[0] + ".wimf"
            else: out_name = filename 
            
            in_ext = os.path.splitext(in_file)[1].lower()
            if in_ext in ['.wimf', '.wif', '.awif']:
                out_name = os.path.splitext(filename)[0] + ".png" 
                
            out_file = os.path.join(args.output, out_name)
            convert(in_file, out_file, compression=comp_mode, quality=args.quality, preset=args.preset, meta=meta, roi=args.roi, depth_map_path=args.depth_map, mip_level=args.mip)
    elif args.chrono:
        print(f"encoding {len(input_files)} states for undo history.")
        from .api import WIMFEncoder
        base_img = Image.open(input_files[0])
        encoder = WIMFEncoder(base_img)
        if args.anti_rot: encoder.set_anti_rot(True)
        for i in range(1, len(input_files)):
            encoder.add_chrono_state(Image.open(input_files[i]))
        
        data = encoder.encode(quality=args.quality, preset=args.preset)
        with _builtins.open(args.output, 'wb') as f: f.write(data)
    elif args.extract_chrono is not None:
        from .api import WIMFDecoder
        decoder = WIMFDecoder(input_files[0])
        img = decoder.decode_chrono_state(args.extract_chrono)
        img.pil.save(args.output)
    else:
        convert(input_files[0], args.output, compression=comp_mode, quality=args.quality, preset=args.preset, meta=meta, roi=args.roi, depth_map_path=args.depth_map, mip_level=args.mip)

if __name__ == "__main__":
    main()
