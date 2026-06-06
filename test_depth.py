import numpy as np
from wimf import saveImage, loadImage
import os

def generate_test_wimf():
    w, h = 256, 256
    channels = 5 # RGBA + Depth
    
    pixels = np.zeros((h, w, channels), dtype=np.uint8)
    
    # R, G, B
    x, y = np.meshgrid(np.arange(w), np.arange(h))
    pixels[..., 0] = (x % 256)
    pixels[..., 1] = (y % 256)
    pixels[..., 2] = ((x + y) % 256)
    
    # Alpha (Circle in the middle)
    cx, cy = w // 2, h // 2
    r = 60
    mask = (x - cx)**2 + (y - cy)**2 < r**2
    pixels[..., 3] = 255
    pixels[mask, 3] = 128 # Semi-transparent
    
    # Depth (Gradient from near to far)
    pixels[..., 4] = np.linspace(0, 255, w).astype(np.uint8)[np.newaxis, :]
    
    raw_bytes = pixels.tobytes()
    
    meta = {
        "author": "BenchWare Test",
        "engine": "WIMF Open Suite v18.7",
        "depth": True,
        "gps": "37.7749,-122.4194"
    }
    
    output_path = "test_depth_alpha.wimf"
    saveImage(output_path, w, h, raw_bytes, compression=2, quality=7, metadata=meta, preset="Balanced")
    print(f"Successfully generated {output_path} with 5 channels (RGBA + Depth)!")

if __name__ == "__main__":
    generate_test_wimf()
