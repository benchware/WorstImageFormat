import sys
import argparse
import os
import numpy as np
from PIL import Image
from .api import WIMFDecoder

def render_terminal(wimf_img, width=None):
    img = wimf_img.pil
    w, h = img.size
    if width is None:
        try:
            width = os.get_terminal_size().columns
        except:
            width = 80
            
    # Account for terminal character aspect ratio (~2:1)
    height = int((h / w) * width * 0.5)
    
    # Ensure height is even for half-block rendering
    if height % 2 != 0:
        height -= 1
        
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    img = img.convert('RGB')
    arr = np.array(img)
    
    # Render using upper half block (▀)
    for y in range(0, height, 2):
        line = ""
        for x in range(width):
            r1, g1, b1 = arr[y, x]
            r2, g2, b2 = arr[y+1, x] if y+1 < height else (0,0,0)
            # Foreground (top half), Background (bottom half)
            line += f"\033[38;2;{r1};{g1};{b1}m\033[48;2;{r2};{g2};{b2}m▀"
        print(line + "\033[0m")
        
def main():
    parser = argparse.ArgumentParser(description="WIMF Terminal Viewer")
    parser.add_argument("-i", "--input", required=True, help="WIMF file to display")
    parser.add_argument("-w", "--width", type=int, help="Override terminal width")
    args = parser.parse_args()
    
    try:
        decoder = WIMFDecoder(args.input)
        # Use target_layer 1 for fast preview in terminal
        wimf_img = decoder.decode(target_layer=1)
        render_terminal(wimf_img, args.width)
        print(f"\n[WIMF-CAT] Viewed: {args.input} ({decoder.width}x{decoder.height})")
    except Exception as e:
        print(f"[WIMF-CAT] Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
